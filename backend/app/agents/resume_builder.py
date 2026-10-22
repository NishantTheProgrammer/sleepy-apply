import os
import re
import json
from datetime import datetime, timezone
import structlog
from bson import ObjectId
from app.db.client import get_db
from app.templates.default import DefaultATSResumeTemplate
from app.providers.factory import AIProviderFactory
from app.models.settings import UserSettings

logger = structlog.get_logger()

RESUME_TAILOR_PROMPT = """You are an elite ATS resume strategist and executive technical recruiter.
Your mission is to tailor the candidate's resume for the target job with MAXIMUM ACCURACY, RELEVANCE, and ATS IMPACT.

TARGET JOB DETAILS:
- Target Role: {job_title}
- Target Company: {company}
- Key Required / Preferred Skills: {required_skills}
- Job Description Context:
{job_description}

CANDIDATE'S AUTHENTIC BACKGROUND:
- Verified Matching Skills: {matching_skills}
- All Candidate Skills: {all_skills}
- Current Summary: {current_summary}
- Real Work Experience History:
{experience_summary}
- Real Personal / Independent Projects:
{projects_summary}

STRICT ACCURACY & RELEVANCE RULES:
1. ZERO HALLUCINATION (100% GROUNDED): You must ONLY use the candidate's real work history, roles, companies, verified skills, and authentic projects. Never invent employers, fake degrees, fabricated metrics, or claim unverified technologies.
2. MAKE RELEVANT THINGS BOLD: Wrap all matching skills, key frameworks, relevant architectures, and measurable metrics in markdown bold: **keyword** (e.g. **NodeJS**, **MongoDB**, **REST APIs**, **Microservices**, **40%**).
3. PROFESSIONAL SUMMARY:
   - 2-3 concise, high-impact sentences.
   - Explicitly position the candidate for **{job_title}** at **{company}**.
   - Bold the target title and key matching tech stack that directly answers the job's main technical requirements.
4. TAILORED EXPERIENCE HIGHLIGHTS:
   - For each role listed in the history, provide 2-3 tailored bullet points highlighting accomplishments relevant to {job_title}.
   - Lead each bullet with a strong action verb (Engineered, Architected, Optimized, Delivered, Streamlined).
   - Bold relevant technical tools, technologies, and metrics inside each bullet point.
5. SELECT & TAILOR RELEVANT PROJECTS (CRITICAL):
   - Evaluate the candidate's authentic projects against {job_title} and {required_skills}.
   - SELECT ONLY 2 TO 3 PROJECTS that directly demonstrate relevant skills for the target role.
   - COMPLETELY OMIT / DISCARD irrelevant, outdated, or basic academic/college projects (e.g., if applying for a senior/backend role, discard basic school assignments, unrelated mobile apps, or non-matching stacks).
   - Under NO circumstances create fake projects. Only choose from the candidate's authentic projects listed above.
   - For each selected project, refine the description (1-2 sentences) to emphasize accomplishments using target technologies, bolding matching keywords: **keyword**.

Return ONLY a valid JSON object matching this exact schema:
{{
  "tailored_summary": "2-3 sentence impactful summary with **bold** keywords",
  "tailored_experience": [
    {{
      "company": "Exact Company Name",
      "highlights": [
        "Action verb + achievement + **relevant technology** in bold"
      ]
    }}
  ],
  "tailored_projects": [
    {{
      "name": "Exact Name of matching project from candidate's background",
      "technologies": ["matching", "technologies"],
      "description": "Refined 1-2 sentence description with **bold** matching technologies and impact"
    }}
  ]
}}
"""


def select_and_tailor_projects(
    raw_projects: list[dict],
    required_skills: list[str],
    matching_skills: list[str],
    job_title: str,
    company: str = "",
    max_projects: int = 3,
    filter_irrelevant: bool = True,
    ai_projects: list[dict] | None = None,
    bold_enabled: bool = True,
) -> list[dict]:
    """Filter candidate personal projects to keep only those relevant to the target job, discarding irrelevant projects."""
    if not raw_projects:
        return []

    authentic_map = {}
    for p in raw_projects:
        name = (p.get("name") or p.get("title") or "").strip()
        if name:
            authentic_map[name.lower()] = p

    # 1. Match AI-selected projects against authentic candidate projects
    if ai_projects and isinstance(ai_projects, list):
        matched_ai_projects = []
        used_auth_names = set()
        for aip in ai_projects:
            if not isinstance(aip, dict):
                continue
            aip_name = (aip.get("name") or aip.get("title") or "").strip()
            if not aip_name:
                continue
            matched_auth = None
            for auth_name, auth_p in authentic_map.items():
                if auth_name in used_auth_names:
                    continue
                if auth_name in aip_name.lower() or aip_name.lower() in auth_name:
                    matched_auth = auth_p
                    used_auth_names.add(auth_name)
                    break

            if matched_auth:
                proj_copy = dict(matched_auth)
                ai_desc = (aip.get("description") or "").strip()
                desc_to_use = ai_desc if ai_desc else proj_copy.get("description", "")

                if bold_enabled and desc_to_use:
                    for ms in matching_skills:
                        if (
                            len(ms) > 2
                            and ms.lower() in desc_to_use.lower()
                            and f"**{ms}**" not in desc_to_use
                            and f"**{ms.lower()}**" not in desc_to_use.lower()
                        ):
                            pattern = re.compile(rf"\b{re.escape(ms)}\b", re.IGNORECASE)
                            desc_to_use = pattern.sub(f"**{ms}**", desc_to_use)

                proj_copy["description"] = desc_to_use
                if aip.get("technologies") and isinstance(aip["technologies"], list):
                    proj_copy["technologies"] = aip["technologies"]
                matched_ai_projects.append(proj_copy)
                if len(matched_ai_projects) >= max_projects:
                    break

        if matched_ai_projects:
            return matched_ai_projects

    # 2. Rule-based relevance scoring and filtering fallback
    job_words = [
        w.lower()
        for w in re.findall(r"\w+", f"{job_title} {company}")
        if len(w) > 2
        and w.lower()
        not in {
            "and",
            "the",
            "for",
            "with",
            "senior",
            "lead",
            "staff",
            "junior",
            "engineer",
            "developer",
            "specialist",
            "manager",
        }
    ]

    scored_projects = []
    for p in raw_projects:
        p_name = (p.get("name") or p.get("title") or "").strip()
        p_desc = (p.get("description") or "").strip()
        p_tech = [str(t).strip() for t in (p.get("technologies") or p.get("tech_stack") or [])]
        tech_str = " ".join(p_tech).lower()
        full_text = f"{p_name} {p_desc} {tech_str}".lower()

        score = 0
        for ms in matching_skills:
            ms_clean = ms.lower().strip()
            if not ms_clean:
                continue
            if ms_clean in tech_str:
                score += 4
            elif ms_clean in full_text:
                score += 2

        for rs in required_skills:
            rs_clean = rs.lower().strip()
            if not rs_clean:
                continue
            if rs_clean in tech_str:
                score += 3
            elif rs_clean in full_text:
                score += 2

        for jw in job_words:
            if jw in full_text:
                score += 2

        is_academic = any(
            ac in full_text
            for ac in ["college project", "academic project", "class project", "university project", "semester"]
        )
        if is_academic and len(raw_projects) > 2:
            score -= 5

        scored_projects.append((score, len(p_tech), len(p_desc), p))

    scored_projects.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    if filter_irrelevant:
        positive_scored = [sp[3] for sp in scored_projects if sp[0] > 0]
        if positive_scored:
            selected_raw = positive_scored[:max_projects]
        else:
            non_academic = [
                sp[3]
                for sp in scored_projects
                if not any(
                    ac in (sp[3].get("description", "") + " " + (sp[3].get("name") or "")).lower()
                    for ac in ["college project", "academic project", "semester"]
                )
            ]
            pool = non_academic if non_academic else [sp[3] for sp in scored_projects]
            selected_raw = pool[: min(2, max_projects)]
    else:
        selected_raw = [sp[3] for sp in scored_projects[:max_projects]]

    final_projects = []
    for p in selected_raw:
        p_copy = dict(p)
        desc = p_copy.get("description", "")
        if bold_enabled and desc:
            for ms in matching_skills:
                if (
                    len(ms) > 2
                    and ms.lower() in desc.lower()
                    and f"**{ms}**" not in desc
                    and f"**{ms.lower()}**" not in desc.lower()
                ):
                    pattern = re.compile(rf"\b{re.escape(ms)}\b", re.IGNORECASE)
                    desc = pattern.sub(f"**{ms}**", desc)
            p_copy["description"] = desc
        final_projects.append(p_copy)

    return final_projects


class ResumeBuilderAgent:
    """Generates customized, ATS-friendly tailored resume JSON and renders DOCX/PDF."""

    def __init__(self):
        self.template = DefaultATSResumeTemplate()

    async def build_tailored_resume(
        self,
        user_id: str,
        job_id: str,
        user_settings: UserSettings | None = None,
        template: str | None = None,
    ) -> dict | None:
        db = get_db()
        profile = await db.profiles.find_one({"user_id": ObjectId(user_id)})
        job = await db.jobs.find_one({"_id": ObjectId(job_id)})

        if not profile or not job:
            logger.warning("Cannot tailor resume: profile or job not found", user_id=user_id, job_id=job_id)
            return None

        job_title = job.get("title") or "Software Engineer"
        company = job.get("company") or "Company"
        required_skills = job.get("required_skills", []) or []

        # Extract all candidate skills
        candidate_skills_list = []
        raw_skills = profile.get("skills", {})
        if isinstance(raw_skills, dict):
            for items in raw_skills.values():
                candidate_skills_list.extend(items)
        elif isinstance(raw_skills, list):
            candidate_skills_list.extend(raw_skills)

        # Match skills against JD
        matching_skills = []
        for cs in candidate_skills_list:
            if any(cs.lower() == req.lower() or req.lower() in cs.lower() or cs.lower() in req.lower() for req in required_skills):
                if cs not in matching_skills:
                    matching_skills.append(cs)

        # Load user settings if not passed
        if not user_settings:
            settings_doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
            if settings_doc:
                try:
                    user_settings = UserSettings(**settings_doc)
                except Exception:
                    pass

        tailored_summary = profile.get("summary", "")
        tailored_experience = None
        tailored_projects = None
        ai_tailored = False

        app_prefs = user_settings.application_preferences if user_settings else None
        tailor_temp = float(getattr(app_prefs, "tailoring_temperature", 0.2) if app_prefs else 0.2)
        max_bullets = int(getattr(app_prefs, "max_bullets_per_role", 5) if app_prefs else 5)
        bold_enabled = bool(getattr(app_prefs, "bold_matching_keywords", True) if app_prefs else True)
        filter_projects = bool(getattr(app_prefs, "filter_irrelevant_projects", True) if app_prefs else True)
        max_projects = int(getattr(app_prefs, "max_tailored_projects", 3) if app_prefs else 3)

        raw_projects = profile.get("projects", [])

        if user_settings and user_settings.ai_provider:
            try:
                provider = AIProviderFactory.resolve(user_settings)

                # Format candidate experience summary for prompt
                raw_exp = profile.get("experience", [])
                exp_summary_lines = []
                for exp in raw_exp[:6]:
                    co = exp.get("company", "Company")
                    ti = exp.get("jobTitle") or exp.get("title", "Role")
                    bullets = exp.get("responsibilities") or exp.get("highlights") or []
                    b_str = "; ".join(bullets[:max_bullets]) if bullets else exp.get("description", "")
                    exp_summary_lines.append(f"- {ti} at {co}: {b_str}")
                exp_summary_text = "\n".join(exp_summary_lines) or "Software engineering experience building web applications and REST APIs."

                # Format candidate projects summary for prompt
                proj_summary_lines = []
                for p in raw_projects[:8]:
                    p_name = p.get("name") or p.get("title") or "Project"
                    p_tech = ", ".join(p.get("technologies") or p.get("tech_stack") or [])
                    p_desc = p.get("description", "")
                    p_str = f"- {p_name}"
                    if p_tech:
                        p_str += f" ({p_tech})"
                    if p_desc:
                        p_str += f": {p_desc[:180]}"
                    proj_summary_lines.append(p_str)
                projects_summary_text = "\n".join(proj_summary_lines) or "None listed."

                job_desc_raw = job.get("description") or ""
                job_desc_clean = " ".join(job_desc_raw.split())[:2000] if job_desc_raw else "Build robust, scalable software applications and collaborate across engineering teams."

                prompt = RESUME_TAILOR_PROMPT.format(
                    job_title=job_title,
                    company=company,
                    required_skills=", ".join(required_skills[:12]) if required_skills else "relevant engineering skills",
                    job_description=job_desc_clean,
                    matching_skills=", ".join(matching_skills) if matching_skills else "core software engineering fundamentals",
                    all_skills=", ".join(candidate_skills_list[:25]),
                    current_summary=profile.get("summary", "") or "Experienced software engineer",
                    experience_summary=exp_summary_text,
                    projects_summary=projects_summary_text,
                )

                resp = await provider.complete([{"role": "user", "content": prompt}], temperature=tailor_temp)

                # Try parsing JSON response
                json_match = re.search(r"\{[\s\S]*\}", resp)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    if parsed.get("tailored_summary"):
                        tailored_summary = parsed["tailored_summary"].strip()
                        ai_tailored = True
                    if parsed.get("tailored_experience") and isinstance(parsed["tailored_experience"], list):
                        tailored_experience = parsed["tailored_experience"]
                    if parsed.get("tailored_projects") and isinstance(parsed["tailored_projects"], list):
                        tailored_projects = parsed["tailored_projects"]
                elif resp and len(resp.strip()) > 30 and "{" not in resp:
                    tailored_summary = resp.strip()
                    ai_tailored = True
            except Exception as e:
                logger.warning("AI resume tailoring failed, using rule-based synthesis with bolding", error=str(e))

        if not ai_tailored:
            bold_matching = [f"**{s}**" for s in matching_skills[:5]]
            key_stack = ", ".join(bold_matching) if bold_matching else "**modern web technologies** and **scalable system architectures**"
            tailored_summary = (
                f"Results-driven **{job_title}** with proven expertise in {key_stack}. "
                f"Demonstrated track record of designing high-reliability applications, optimized to drive measurable technical impact "
                f"as **{job_title}** at **{company}**."
            )

        # Merge tailored experience highlights & bold relevant skills in experience bullets
        final_experience = []
        raw_experience = profile.get("experience", [])
        tailored_exp_map = {}
        if tailored_experience:
            for te in tailored_experience:
                if isinstance(te, dict) and te.get("company"):
                    co_name = te["company"].strip().lower()
                    tailored_exp_map[co_name] = te.get("highlights", [])

        for exp in raw_experience:
            exp_copy = dict(exp)
            co_key = exp_copy.get("company", "").strip().lower()
            resps_to_process = (
                tailored_exp_map[co_key]
                if co_key in tailored_exp_map and tailored_exp_map[co_key]
                else (exp_copy.get("responsibilities") or exp_copy.get("highlights") or [])
            )
            bolded_resps = []
            for r in resps_to_process:
                bolded_r = str(r)
                for ms in matching_skills:
                    if len(ms) > 2 and ms.lower() in bolded_r.lower() and f"**{ms}**" not in bolded_r and f"**{ms.lower()}**" not in bolded_r.lower():
                        pattern = re.compile(rf"\b{re.escape(ms)}\b", re.IGNORECASE)
                        bolded_r = pattern.sub(f"**{ms}**", bolded_r)
                bolded_resps.append(bolded_r)

            if bolded_resps:
                exp_copy["responsibilities"] = bolded_resps
                exp_copy["highlights"] = bolded_resps
            final_experience.append(exp_copy)

        # Filter & tailor personal projects to keep only relevant ones
        final_projects = select_and_tailor_projects(
            raw_projects=raw_projects,
            required_skills=required_skills,
            matching_skills=matching_skills,
            job_title=job_title,
            company=company,
            max_projects=max_projects,
            filter_irrelevant=filter_projects,
            ai_projects=tailored_projects,
            bold_enabled=bold_enabled,
        )

        # Re-order/boost matching skills to the front of skills
        tailored_skills = {}
        if isinstance(raw_skills, dict):
            for cat, items in raw_skills.items():
                boosted = [s for s in items if s in matching_skills]
                others = [s for s in items if s not in matching_skills]
                tailored_skills[cat] = boosted + others
        elif isinstance(raw_skills, list):
            boosted = [s for s in raw_skills if s in matching_skills]
            others = [s for s in raw_skills if s not in matching_skills]
            tailored_skills = boosted + others

        # Selected template
        selected_template_id = template or profile.get("selected_template") or "default"

        now = datetime.now(timezone.utc)
        resume_content = {
            "job_id": str(job_id),
            "job_title": job_title,
            "company": company,
            "tailored_summary": tailored_summary,
            "matching_skills": matching_skills,
            "required_skills": required_skills,
            "personal": profile.get("personal", {}),
            "summary": tailored_summary,
            "skills": tailored_skills if tailored_skills else raw_skills,
            "experience": final_experience,
            "education": profile.get("education", []),
            "projects": final_projects,
            "achievements": profile.get("achievements", []),
            "template": selected_template_id,
            "generated_at": now.isoformat(),
        }

        def _sanitize_for_mongo(obj):
            if isinstance(obj, ObjectId):
                return str(obj)
            if isinstance(obj, dict):
                return {k: _sanitize_for_mongo(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize_for_mongo(v) for v in obj]
            return obj

        resume_content = _sanitize_for_mongo(resume_content)

        # Render DOCX output
        storage_dir = os.path.join(os.getcwd(), "storage", "resumes", str(user_id))
        os.makedirs(storage_dir, exist_ok=True)
        docx_path = os.path.join(storage_dir, f"resume_{job_id}_{selected_template_id}.docx")

        try:
            from app.templates.manager import render_docx_for_profile
            tailored_profile_context = {
                **profile,
                "summary": tailored_summary,
                "skills": tailored_skills if tailored_skills else raw_skills,
                "experience": final_experience,
                "projects": final_projects,
                "matching_skills": matching_skills,
            }
            docx_stream = render_docx_for_profile(selected_template_id, tailored_profile_context)
            with open(docx_path, "wb") as f:
                f.write(docx_stream.getvalue())
        except Exception as e:
            logger.error("Failed to render tailored resume DOCX", error=str(e), job_id=job_id)
            docx_path = None


        # Render PDF output
        pdf_path = os.path.join(storage_dir, f"resume_{job_id}.pdf")
        try:
            self.template.render_pdf(resume_content, pdf_path)
        except Exception as e:
            logger.error("Failed to render resume PDF", error=str(e), job_id=job_id)
            pdf_path = None

        # 1. Store in db.resumes collection
        resume_doc = {
            "user_id": ObjectId(user_id),
            "job_id": ObjectId(job_id),
            "template": selected_template_id,
            "content": resume_content,
            "pdf_path": pdf_path,
            "docx_path": docx_path,
            "generated_at": now.isoformat(),
        }
        res = await db.resumes.update_one(
            {"user_id": ObjectId(user_id), "job_id": ObjectId(job_id)},
            {"$set": resume_doc},
            upsert=True,
        )
        if res.upserted_id:
            resume_doc["_id"] = str(res.upserted_id)

        # 2. Store directly against the job-user match listing in db.job_matches
        await db.job_matches.update_one(
            {"user_id": ObjectId(user_id), "job_id": ObjectId(job_id)},
            {
                "$set": {
                    "tailored_resume": resume_content,
                    "resume_generated_at": now.isoformat(),
                    "resume_docx_path": docx_path,
                },
                "$setOnInsert": {
                    "status": "pending",
                    "compatibility_score": 75,
                },
            },
            upsert=True,
        )

        logger.info(
            "Tailored resume JSON generated and stored against job-user match",
            user_id=user_id,
            job_id=job_id,
            company=company,
            title=job_title,
            matching_skills_count=len(matching_skills),
        )
        return resume_doc
