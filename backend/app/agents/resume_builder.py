import os
from datetime import datetime, timezone
import structlog
from bson import ObjectId
from app.db.client import get_db
from app.templates.default import DefaultATSResumeTemplate
from app.providers.factory import AIProviderFactory
from app.models.settings import UserSettings

logger = structlog.get_logger()

RESUME_TAILOR_PROMPT = """Tailor this candidate summary for a job application.
Job Title: {job_title}
Company: {company}
Required Skills: {job_skills}
Current Summary: {summary}

Write a 2-3 sentence impactful professional summary emphasizing how the candidate's skills make them an ideal fit for {job_title} at {company}:"""


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

        # Tailor summary: try AI first if configured, else use rule-based synthesis
        tailored_summary = profile.get("summary", "")
        if not user_settings:
            settings_doc = await db.settings.find_one({"user_id": ObjectId(user_id)})
            if settings_doc:
                try:
                    user_settings = UserSettings(**settings_doc)
                except Exception:
                    pass

        ai_tailored = False
        if user_settings and user_settings.ai_provider:
            try:
                provider = AIProviderFactory.resolve(user_settings)
                prompt = RESUME_TAILOR_PROMPT.format(
                    job_title=job_title,
                    company=company,
                    job_skills=", ".join(required_skills[:8]) if required_skills else "relevant engineering skills",
                    summary=tailored_summary or "Full Stack Developer with experience in web applications",
                )
                resp = await provider.complete([{"role": "user", "content": prompt}], temperature=0.3)
                if resp and resp.strip():
                    tailored_summary = resp.strip()
                    ai_tailored = True
            except Exception as e:
                logger.warning("AI resume summary tailoring failed, using rule-based tailoring", error=str(e))

        if not ai_tailored:
            key_stack = ", ".join(matching_skills[:5]) if matching_skills else "modern web technologies and scalable system architectures"
            tailored_summary = (
                f"Results-driven Engineer with expertise in {key_stack}. "
                f"Demonstrated track record of designing high-reliability applications, optimized to drive technical impact "
                f"as {job_title} at {company}."
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
            "experience": profile.get("experience", []),
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
