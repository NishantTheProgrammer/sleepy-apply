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

STRICT ACCURACY & RELEVANCE RULES:
1. ZERO HALLUCINATION (100% GROUNDED): You must ONLY use the candidate's real work history, roles, companies, and verified skills. Never invent employers, fake degrees, fabricated metrics, or claim unverified technologies.
2. MAKE RELEVANT THINGS BOLD: Wrap all matching skills, key frameworks, relevant architectures, and measurable metrics in markdown bold: **keyword** (e.g. **NodeJS**, **MongoDB**, **REST APIs**, **Microservices**, **40%**).
3. PROFESSIONAL SUMMARY:
   - 2-3 concise, high-impact sentences.
   - Explicitly position the candidate for **{job_title}** at **{company}**.
   - Bold the target title and key matching tech stack that directly answers the job's main technical requirements.
4. TAILORED EXPERIENCE HIGHLIGHTS:
   - For each role listed in the history, provide 2-3 tailored bullet points highlighting accomplishments relevant to {job_title}.
   - Lead each bullet with a strong action verb (Engineered, Architected, Optimized, Delivered, Streamlined).
   - Bold relevant technical tools, technologies, and metrics inside each bullet point.

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
  ]
}}
"""


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
        ai_tailored = False

        if user_settings and user_settings.ai_provider:
            try:
                provider = AIProviderFactory.resolve(user_settings)

                # Format candidate experience summary for prompt
                raw_exp = profile.get("experience", [])
                exp_summary_lines = []
                for exp in raw_exp[:4]:
                    co = exp.get("company", "Company")
                    ti = exp.get("jobTitle") or exp.get("title", "Role")
                    bullets = exp.get("responsibilities") or exp.get("highlights") or []
                    b_str = "; ".join(bullets[:3]) if bullets else exp.get("description", "")
                    exp_summary_lines.append(f"- {ti} at {co}: {b_str}")
                exp_summary_text = "\n".join(exp_summary_lines) or "Software engineering experience building web applications and REST APIs."

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
                )

                resp = await provider.complete([{"role": "user", "content": prompt}], temperature=0.2)

                # Try parsing JSON response
                json_match = re.search(r"\{[\s\S]*\}", resp)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    if parsed.get("tailored_summary"):
                        tailored_summary = parsed["tailored_summary"].strip()
                        ai_tailored = True
                    if parsed.get("tailored_experience") and isinstance(parsed["tailored_experience"], list):
                        tailored_experience = parsed["tailored_experience"]
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
            "projects": profile.get("projects", []),
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
