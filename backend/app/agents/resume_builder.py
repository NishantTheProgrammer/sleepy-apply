import os
import re
import json
from datetime import datetime, timezone
from typing import Any
import structlog
from bson import ObjectId

from app.db.client import get_db
from app.templates.default import DefaultATSResumeTemplate
from app.providers.factory import AIProviderFactory
from app.models.settings import UserSettings
from app.agents.evidence_mapper import EvidenceMapper, EvidenceMappingResult
from app.agents.hallucination_guard import HallucinationGuard, ValidationResult

logger = structlog.get_logger()

RESUME_TAILOR_PROMPT = """You are a senior technical hiring manager and staff engineer tailoring a candidate's resume for a specific software engineering role.
Your mission is to maximize ATS keyword alignment and technical credibility while keeping the output 100% authentic, grounded, and human-written.

TARGET JOB DETAILS:
- Target Role: {job_title}
- Target Company: {company}
- Key Required Skills: {required_skills}
- Job Description Context:
{job_description}

EVIDENCE MAPPING & FACTUAL BOUNDARIES (COMPLY STRICTLY):
1. VERIFIED MATCHED SKILLS (PROVEN IN CANDIDATE BACKGROUND):
{matched_skills_evidence}

2. PARTIALLY MATCHED & PROJECT-LEVEL SKILLS (STRICT ATTRIBUTION):
{partial_skills_evidence}
* RULE: If a technology (e.g. Spring Boot, Django, Flutter) is from an independent or academic project, describe it accurately as hands-on project experience. NEVER claim multi-year professional employment for project-only technologies!

3. UNVERIFIED / MISSING JD REQUIREMENTS (DO NOT CLAIM):
{missing_skills_list}
* CRITICAL RULE: The candidate has ZERO verified evidence for these technologies. You MUST NOT claim them, put them in the headline, summary, experience highlights, or skills!

4. OVERALL EXPERIENCE GROUNDING:
- Candidate has {overall_years:g} years of overall software development experience.
- NEVER inflate experience (do not claim >{overall_years:g} years or copy JD years like 6-8 years).
- NEVER convert overall Full Stack experience into tech-specific experience (e.g. never say "{overall_years:g}+ years of Java developer").

5. LEADERSHIP & TEAM SIZES:
- Candidate's verified record states: "Conducting interviews, mentored junior developers, developing REST APIs, reviewing pull requests."
- DO NOT invent team sizes (e.g. do NOT write "mentored team of 4-6 engineers"). State "mentored junior developers and conducted technical interviews".

6. EDUCATION FIDELITY:
- Candidate holds: {education_summary}.
- Do NOT alter degrees or claim B.Tech/BE.

7. BANNED AI BUZZWORDS:
- Do NOT use: "spearheaded", "synergized", "leveraged", "delve", "pivotal", "transformative", "game-changing", "visionary", "testament to", "holistic", "cutting-edge", or "revolutionized".
- Use concrete engineering action verbs: Built, Designed, Implemented, Refactored, Maintained, Optimized, Automated, Integrated, Migrated, Deployed, Resolved, Scaled.

8. GOOGLE X-Y-Z FORMULA (REALISTIC OUTCOMES):
- Format bullets following: Accomplished [X], as measured by [Y], by doing [Z].
- Use authentic metrics from candidate notes (e.g. "handling data for 4000+ urban local bodies", "10+ scalable applications", "solving 450+ LeetCode problems").
- NEVER invent corporate financial figures (e.g. "$40M revenue increase", "99.999% efficiency leap").

Return ONLY a valid JSON object matching this exact schema:
{{
  "target_headline": "Professional Role Headline | Primary Verified Tech Stacks",
  "tailored_summary": "2-3 sentence impactful summary accurately reflecting overall experience and verified strengths with selective **bold** keywords",
  "tailored_experience": [
    {{
      "company": "Exact Company Name",
      "highlights": [
        "Action verb + technical accomplishment + realistic outcome with selective **bold** verified tech"
      ]
    }}
  ],
  "tailored_projects": [
    {{
      "name": "Exact Name of matching project from candidate's background",
      "technologies": ["matching", "technologies"],
      "description": "Realistic 1-2 sentence description highlighting verified tech and architecture"
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
    """Filter candidate personal projects to prioritize high-relevance projects while preserving authenticity."""
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
                    # Clean tech tags
                    clean_ai_tech = []
                    seen_t = set()
                    for t in aip["technologies"]:
                        c = str(t).strip()
                        if c and c.lower() not in seen_t:
                            seen_t.add(c.lower())
                            clean_ai_tech.append(c)
                    proj_copy["technologies"] = clean_ai_tech
                    proj_copy["tech_stack"] = clean_ai_tech

                # Ensure backwards-compatible fields
                proj_copy["title"] = proj_copy.get("name") or proj_copy.get("title")
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
            "and", "the", "for", "with", "senior", "lead", "staff", "junior", "engineer", "developer", "specialist", "manager"
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
                score += 5
            elif ms_clean in full_text:
                score += 2

        for rs in required_skills:
            rs_clean = rs.lower().strip()
            if not rs_clean:
                continue
            if rs_clean in tech_str:
                score += 4
            elif rs_clean in full_text:
                score += 2

        # Special boost for backend matching projects
        if "backend" in job_title.lower() or "java" in " ".join(required_skills).lower():
            if "spring" in full_text or "django" in full_text:
                score += 4
            if "node" in full_text and "api" in full_text:
                score += 3

        for jw in job_words:
            if jw in full_text:
                score += 2

        is_academic = any(
            ac in full_text
            for ac in ["college project", "academic project", "class project", "university project", "semester"]
        )
        if is_academic and len(raw_projects) > 2:
            score -= 3

        scored_projects.append((score, len(p_tech), len(p_desc), p))

    scored_projects.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    if filter_irrelevant:
        positive_scored = [sp[3] for sp in scored_projects if sp[0] > 0]
        if positive_scored:
            selected_raw = positive_scored[:max_projects]
        else:
            selected_raw = [sp[3] for sp in scored_projects[: min(2, max_projects)]]
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

        # Backwards compatible aliases
        p_copy["title"] = p_copy.get("name") or p_copy.get("title")
        p_copy["tech_stack"] = p_copy.get("technologies") or p_copy.get("tech_stack")
        final_projects.append(p_copy)

    return final_projects


def preserve_and_prioritize_experience_bullets(
    company_name: str,
    original_bullets: list[str],
    ai_bullets: list[str] | None,
    matching_skills: list[str],
    missing_skills: list[str],
    job_title: str = "",
    company: str = "",
    job_description: str = "",
    bold_enabled: bool = True,
) -> list[str]:
    """Preserves critical candidate technical accomplishments, metrics, and integrations,
    eliminates cross-employer attribution bleed, and prioritizes bullets based on JD relevance."""
    co_lower = (company_name or "").strip().lower()
    is_dhwani = "dhwani" in co_lower
    is_maxvision = "max vision" in co_lower

    # 1. Clean and filter AI bullets for cross-employer bleed
    valid_ai_bullets: list[str] = []
    if ai_bullets and isinstance(ai_bullets, list):
        for b in ai_bullets:
            b_str = str(b).strip()
            if not b_str:
                continue
            b_lower = b_str.lower()
            # Dhwani cannot contain Max Vision projects
            if is_dhwani and any(k in b_lower for k in ["mesa-qr", "pay.mesa-qr", "getlivecoach", "kichi-mall", "in1mall", "ionic"]):
                continue
            # Max Vision cannot contain Dhwani projects
            if is_maxvision and any(k in b_lower for k in ["dhwani", "indian partner network", "city finance", "4000+", "4,000+", "urban local bodies", "form.io"]):
                continue
            valid_ai_bullets.append(b_str)

    clean_orig_bullets = [str(b).strip() for b in (original_bullets or []) if str(b).strip()]

    # 2. Information Restoration: Ensure critical candidate details are not omitted
    final_raw_bullets: list[str] = []
    if valid_ai_bullets:
        combined_ai_text = " ".join(valid_ai_bullets).lower()

        for b in valid_ai_bullets:
            bullet_fixed = b
            # If bullet mentions query optimization but dropped materialized views, restore it
            if "query optimization" in bullet_fixed.lower() and "materialized view" not in bullet_fixed.lower():
                bullet_fixed = re.sub(
                    r"query optimization(?:\s+and\s+|\s*,\s*)",
                    "query optimization, materialized views, and ",
                    bullet_fixed,
                    flags=re.IGNORECASE,
                )
            final_raw_bullets.append(bullet_fixed)

        # Check for omitted original critical accomplishments and restore them:
        if is_dhwani:
            # City Finance (4000+ ULBs)
            if not any(k in combined_ai_text for k in ["city finance", "4000+", "4,000+", "urban local bodies"]):
                city_fin_bullet = next(
                    (ob for ob in clean_orig_bullets if "4000+" in ob or "urban local bodies" in ob.lower() or "city finance" in ob.lower()),
                    None,
                )
                if city_fin_bullet and city_fin_bullet not in final_raw_bullets:
                    final_raw_bullets.append(city_fin_bullet)

            # Form.io / SendGrid integrations
            if not any("form.io" in combined_ai_text or "sendgrid" in combined_ai_text for _ in [1]):
                formio_bullet = next((ob for ob in clean_orig_bullets if "form.io" in ob.lower() or "sendgrid" in ob.lower()), None)
                if formio_bullet and not any("indian partner network" in fb.lower() for fb in final_raw_bullets):
                    final_raw_bullets.append(formio_bullet)

            # Materialized views / Query optimization
            if not any("materialized view" in fb.lower() for fb in final_raw_bullets):
                db_bullet = next((ob for ob in clean_orig_bullets if "materialized view" in ob.lower()), None)
                if db_bullet and db_bullet not in final_raw_bullets:
                    final_raw_bullets.append(db_bullet)

        elif is_maxvision:
            # Stripe split payment / pay.mesa-qr.com
            if not any("stripe split payment" in combined_ai_text or "mesa-qr" in combined_ai_text for _ in [1]):
                mesa_bullet = next((ob for ob in clean_orig_bullets if "mesa-qr" in ob.lower() or "split payment" in ob.lower()), None)
                if mesa_bullet and mesa_bullet not in final_raw_bullets:
                    final_raw_bullets.append(mesa_bullet)

            # WooCommerce / Kichi-Mall
            if not any("woocommerce" in combined_ai_text or "kichi-mall" in combined_ai_text for _ in [1]):
                woo_bullet = next((ob for ob in clean_orig_bullets if "woocommerce" in ob.lower() or "kichi-mall" in ob.lower()), None)
                if woo_bullet and woo_bullet not in final_raw_bullets:
                    final_raw_bullets.append(woo_bullet)
    else:
        final_raw_bullets = list(clean_orig_bullets)

    # 3. Strip missing technologies and bold verified matching technologies
    processed_bullets: list[str] = []
    for bullet in final_raw_bullets:
        b_clean = bullet
        for ms in missing_skills:
            if len(ms) > 2:
                b_clean = re.sub(rf"\b{re.escape(ms)}\b", "", b_clean, flags=re.IGNORECASE)

        if bold_enabled:
            for ms in matching_skills:
                if (
                    len(ms) > 2
                    and ms.lower() in b_clean.lower()
                    and f"**{ms}**" not in b_clean
                    and f"**{ms.lower()}**" not in b_clean.lower()
                ):
                    pattern = re.compile(rf"\b{re.escape(ms)}\b", re.IGNORECASE)
                    b_clean = pattern.sub(f"**{ms}**", b_clean)

        b_clean = " ".join(b_clean.split()).strip()
        if b_clean and b_clean not in processed_bullets:
            processed_bullets.append(b_clean)

    # 4. Relevance Prioritization (Reorder bullets based on target JD relevance)
    target_context = f"{job_title} {company} {job_description}".lower()

    def bullet_relevance_score(b_text: str) -> int:
        score = 0
        b_lower = b_text.lower()

        # Target matching skills (+5 each)
        for s in matching_skills:
            if len(s) > 2 and s.lower() in b_lower:
                score += 5

        # Backend / Database / Optimization keywords (+4 each)
        if any(w in target_context for w in ["backend", "java", "sql", "database", "api"]):
            for kw in ["query optimization", "materialized views", "postgresql", "mysql", "sql", "rest apis", "rest api", "bulk upload", "performance"]:
                if kw in b_lower:
                    score += 4

        # E-commerce / Payment keywords (+4 each)
        if any(w in target_context for w in ["ecommerce", "e-commerce", "payment", "critical services"]):
            for kw in ["stripe", "stripe split payment", "woocommerce", "e-commerce", "qr code"]:
                if kw in b_lower:
                    score += 4

        # Mentoring / Leadership (+3 each)
        if any(w in target_context for w in ["mentor", "lead", "team"]):
            if "mentor" in b_lower or "interview" in b_lower:
                score += 3

        return score

    processed_bullets.sort(key=bullet_relevance_score, reverse=True)
    return processed_bullets


class ResumeBuilderAgent:
    """Generates evidence-grounded, ATS-friendly tailored resumes and renders DOCX/PDF."""

    def __init__(self):
        self.template = DefaultATSResumeTemplate()
        self.evidence_mapper = EvidenceMapper()
        self.hallucination_guard = HallucinationGuard()

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

        # 1. Rigorous JD-to-candidate evidence mapping
        evidence_result: EvidenceMappingResult = self.evidence_mapper.map_evidence(profile, job)
        cand_index = evidence_result.candidate_index
        skills_cls = evidence_result.skills_classification

        job_title = job.get("title") or "Software Engineer"
        company = job.get("company") or "Company"
        required_skills = job.get("required_skills", []) or []

        matching_skills = skills_cls.matched_skills
        partial_skills = skills_cls.partially_matched_skills
        missing_skills = skills_cls.missing_skills

        # All candidate skills list
        candidate_skills_list = []
        raw_skills = profile.get("skills", {})
        if isinstance(raw_skills, dict):
            for items in raw_skills.values():
                candidate_skills_list.extend(items)
        elif isinstance(raw_skills, list):
            candidate_skills_list.extend(raw_skills)

        # Load user settings if not passed
        if not user_settings:
            settings_doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
            if settings_doc:
                try:
                    user_settings = UserSettings(**settings_doc)
                except Exception:
                    pass

        app_prefs = user_settings.application_preferences if user_settings else None
        tailor_temp = float(getattr(app_prefs, "tailoring_temperature", 0.15) if app_prefs else 0.15)
        max_bullets = int(getattr(app_prefs, "max_bullets_per_role", 4) if app_prefs else 4)
        bold_enabled = bool(getattr(app_prefs, "bold_matching_keywords", True) if app_prefs else True)
        filter_projects = bool(getattr(app_prefs, "filter_irrelevant_projects", True) if app_prefs else True)
        max_projects = int(getattr(app_prefs, "max_tailored_projects", 3) if app_prefs else 3)

        raw_projects = profile.get("projects", [])
        raw_experience = profile.get("experience", [])

        # Format evidence summaries for prompt
        matched_evidence_lines = []
        for m in evidence_result.mappings:
            if m.status == "MATCHED":
                matched_evidence_lines.append(f"- {m.requirement} ({m.source_entity}): {m.evidence_text}")
        matched_evidence_text = "\n".join(matched_evidence_lines) or "- Full stack development, REST APIs, SQL databases"

        partial_evidence_lines = []
        for m in evidence_result.mappings:
            if m.status == "PARTIAL":
                partial_evidence_lines.append(f"- {m.requirement} ({m.source_entity}): {m.evidence_text} [{m.notes}]")
        partial_evidence_text = "\n".join(partial_evidence_lines) or "None."

        missing_skills_text = ", ".join(missing_skills) if missing_skills else "None identified"
        education_summary = ", ".join([f"{e.get('degree')} from {e.get('institution')}" for e in profile.get("education", [])]) or "Computer Applications degree"

        target_headline = ""
        tailored_summary = ""
        tailored_experience = None
        tailored_projects = None
        ai_tailored = False

        if user_settings and user_settings.ai_provider:
            try:
                provider = AIProviderFactory.resolve(user_settings)

                job_desc_raw = job.get("description") or ""
                job_desc_clean = " ".join(job_desc_raw.split())[:2000] if job_desc_raw else "Build robust backend architectures and collaborative microservices."

                prompt = RESUME_TAILOR_PROMPT.format(
                    job_title=job_title,
                    company=company,
                    required_skills=", ".join(required_skills[:12]) if required_skills else "relevant engineering skills",
                    job_description=job_desc_clean,
                    matched_skills_evidence=matched_evidence_text,
                    partial_skills_evidence=partial_evidence_text,
                    missing_skills_list=missing_skills_text,
                    overall_years=cand_index.overall_years,
                    education_summary=education_summary,
                )

                resp = await provider.complete([{"role": "user", "content": prompt}], temperature=tailor_temp)

                json_match = re.search(r"\{[\s\S]*\}", resp)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    if parsed.get("target_headline"):
                        target_headline = parsed["target_headline"].strip()
                    if parsed.get("tailored_summary"):
                        tailored_summary = parsed["tailored_summary"].strip()
                        ai_tailored = True
                    if parsed.get("tailored_experience") and isinstance(parsed["tailored_experience"], list):
                        tailored_experience = parsed["tailored_experience"]
                    if parsed.get("tailored_projects") and isinstance(parsed["tailored_projects"], list):
                        tailored_projects = parsed["tailored_projects"]
            except Exception as e:
                logger.warning("AI resume tailoring failed, using rule-based synthesis", error=str(e))

        # ------------------------------------------------------------------
        # Deterministic Grounding & Headline Synthesis
        # ------------------------------------------------------------------
        # Construct verified headline without missing technologies (e.g. NEVER claim CI/CD)
        if not target_headline:
            verified_headline_tech = []
            for ms in matching_skills:
                if ms.lower() not in {m.lower() for m in missing_skills}:
                    verified_headline_tech.append(ms)

            # Add primary backend stack if missing
            for fallback_tech in ["Node.js", "PostgreSQL", "REST APIs", "SQL", "System Design"]:
                if fallback_tech in cand_index.all_known_technologies and fallback_tech not in verified_headline_tech:
                    verified_headline_tech.append(fallback_tech)

            # Note project-level tech appropriately
            tech_str = ", ".join(verified_headline_tech[:3])
            if any("spring" in t.lower() for t in partial_skills):
                tech_str += " & Spring Boot Projects"
            target_headline = f"{job_title} | {tech_str}"

        # Strip any unverified missing skills that leaked into target_headline
        for ms in missing_skills:
            if len(ms) > 2:
                target_headline = re.sub(rf"\b{re.escape(ms)}\b", "", target_headline, flags=re.IGNORECASE)
        target_headline = re.sub(r"[\s,&|]+$", "", target_headline).strip()
        target_headline = re.sub(r"\|\s*\|", "|", target_headline).strip()

        # ------------------------------------------------------------------
        # Deterministic Summary Synthesis
        # ------------------------------------------------------------------
        if not ai_tailored or not tailored_summary:
            bold_matching = [f"**{s}**" for s in matching_skills[:4] if s.lower() not in {m.lower() for m in missing_skills}]
            key_stack = ", ".join(bold_matching) if bold_matching else "**Node.js**, **REST APIs**, and **SQL databases**"

            project_tech_note = ""
            if any("spring" in t.lower() for t in partial_skills):
                project_tech_note = " Hands-on project experience developing role-based services with **Spring Boot**."

            tailored_summary = (
                f"Full Stack Developer with **{cand_index.overall_years:g} years** of overall software engineering experience "
                f"delivering scalable systems, high-performance APIs, and database optimizations. Proven track record in {key_stack}, "
                f"query tuning, and microservices architecture.{project_tech_note}"
            )

        # ------------------------------------------------------------------
        # Experience Highlights Assembly
        # ------------------------------------------------------------------
        final_experience = []
        tailored_exp_map = {}
        if tailored_experience:
            for te in tailored_experience:
                if isinstance(te, dict) and te.get("company"):
                    co_name = te["company"].strip().lower()
                    tailored_exp_map[co_name] = te.get("highlights", [])

        for exp in raw_experience:
            exp_copy = dict(exp)
            co_name = exp_copy.get("company", "").strip()
            co_key = co_name.lower()
            orig_bullets = exp_copy.get("responsibilities") or exp_copy.get("highlights") or []
            ai_exp_bullets = tailored_exp_map.get(co_key, [])

            processed_bullets = preserve_and_prioritize_experience_bullets(
                company_name=co_name,
                original_bullets=orig_bullets,
                ai_bullets=ai_exp_bullets,
                matching_skills=matching_skills,
                missing_skills=missing_skills,
                job_title=job_title,
                company=company,
                job_description=job.get("description", ""),
                bold_enabled=bold_enabled,
            )

            if processed_bullets:
                exp_copy["responsibilities"] = processed_bullets
                exp_copy["highlights"] = processed_bullets

            # Ensure backward-compatible title/date fields
            exp_copy["title"] = exp_copy.get("jobTitle") or exp_copy.get("title") or "Software Engineer"
            exp_copy["jobTitle"] = exp_copy["title"]
            exp_copy["start_date"] = exp_copy.get("startDate") or exp_copy.get("start_date") or ""
            exp_copy["startDate"] = exp_copy["start_date"]
            exp_copy["end_date"] = exp_copy.get("endDate") or exp_copy.get("end_date") or ""
            exp_copy["endDate"] = exp_copy["end_date"]
            exp_copy["is_current"] = bool(exp_copy.get("current") or exp_copy.get("is_current"))
            exp_copy["current"] = exp_copy["is_current"]
            final_experience.append(exp_copy)

        # ------------------------------------------------------------------
        # Filter & Prioritize Matching Projects
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # Re-order and Categorize Skills
        # ------------------------------------------------------------------
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

        selected_template_id = template or profile.get("selected_template") or "default"
        now = datetime.now(timezone.utc)

        personal_data = profile.get("personal", {})
        cand_name = personal_data.get("fullName") or personal_data.get("full_name") or "Candidate"

        resume_content = {
            "job_id": str(job_id),
            "job_title": job_title,
            "company": company,
            "target_headline": target_headline,
            "summary": tailored_summary,
            "tailored_summary": tailored_summary,
            "matching_skills": matching_skills,
            "missing_skills": missing_skills,
            "skills_breakdown": {
                "matched_skills": skills_cls.matched_skills,
                "partially_matched_skills": skills_cls.partially_matched_skills,
                "missing_skills": skills_cls.missing_skills,
                "unverified_skills": skills_cls.unverified_skills,
                "additional_relevant_skills": skills_cls.additional_relevant_skills,
            },
            "evidence_mappings": [m.model_dump() for m in evidence_result.mappings],
            "required_skills": required_skills,
            "personal": {
                **personal_data,
                "fullName": cand_name,
                "full_name": cand_name,
            },
            "skills": tailored_skills if tailored_skills else raw_skills,
            "experience": final_experience,
            "education": profile.get("education", []),
            "projects": final_projects,
            "achievements": profile.get("achievements", []),
            "template": selected_template_id,
            "generated_at": now.isoformat(),
        }

        # ------------------------------------------------------------------
        # Post-Generation Hallucination Guard Validation & Sanitization
        # ------------------------------------------------------------------
        val_result: ValidationResult = self.hallucination_guard.validate_and_sanitize(
            tailored_resume=resume_content,
            original_profile=profile,
            evidence_result=evidence_result,
        )

        if val_result.sanitized:
            logger.warning(
                "HallucinationGuard sanitized tailored resume content",
                job_id=job_id,
                critical_count=len(val_result.critical_violations),
            )
            resume_content = val_result.sanitized_content

        resume_content["validation_report"] = {
            "is_valid": val_result.is_valid,
            "sanitized": val_result.sanitized,
            "critical_violations": [v.model_dump() for v in val_result.critical_violations],
            "warnings": [w.model_dump() for w in val_result.warnings],
            "summary": val_result.summary_notes,
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

        # ------------------------------------------------------------------
        # Render Output Files (DOCX & PDF)
        # ------------------------------------------------------------------
        storage_dir = os.path.join(os.getcwd(), "storage", "resumes", str(user_id))
        os.makedirs(storage_dir, exist_ok=True)
        docx_path = os.path.join(storage_dir, f"resume_{job_id}_{selected_template_id}.docx")

        try:
            from app.templates.manager import render_docx_for_profile
            tailored_profile_context = {
                **profile,
                "target_headline": resume_content["target_headline"],
                "summary": resume_content["summary"],
                "skills": resume_content["skills"],
                "experience": resume_content["experience"],
                "projects": resume_content["projects"],
                "matching_skills": resume_content["matching_skills"],
            }
            docx_stream = render_docx_for_profile(selected_template_id, tailored_profile_context)
            with open(docx_path, "wb") as f:
                f.write(docx_stream.getvalue())
        except Exception as e:
            logger.error("Failed to render tailored resume DOCX", error=str(e), job_id=job_id)
            docx_path = None

        pdf_path = os.path.join(storage_dir, f"resume_{job_id}.pdf")
        try:
            self.template.render_pdf(resume_content, pdf_path)
        except Exception as e:
            logger.error("Failed to render resume PDF", error=str(e), job_id=job_id)
            pdf_path = None

        # ------------------------------------------------------------------
        # Store in db.resumes and db.job_matches (Never mutating db.profiles!)
        # ------------------------------------------------------------------
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
            "Evidence-grounded tailored resume stored successfully",
            user_id=user_id,
            job_id=job_id,
            company=company,
            title=job_title,
            matched_skills_count=len(matching_skills),
            is_valid=val_result.is_valid,
        )
        return resume_doc
