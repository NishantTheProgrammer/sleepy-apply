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
    """Generates customized, ATS-friendly resume content and renders PDF."""

    def __init__(self):
        self.template = DefaultATSResumeTemplate()

    async def build_tailored_resume(
        self,
        user_id: str,
        job_id: str,
        user_settings: UserSettings | None = None,
    ) -> dict | None:
        db = get_db()
        profile = await db.profiles.find_one({"user_id": ObjectId(user_id)})
        job = await db.jobs.find_one({"_id": ObjectId(job_id)})

        if not profile or not job:
            return None

        # Tailor summary if AI is available
        tailored_summary = profile.get("summary", "")
        if user_settings and tailored_summary:
            try:
                provider = AIProviderFactory.resolve(user_settings)
                prompt = RESUME_TAILOR_PROMPT.format(
                    job_title=job.get("title"),
                    company=job.get("company"),
                    job_skills=", ".join(job.get("required_skills", [])[:8]),
                    summary=tailored_summary,
                )
                resp = await provider.complete([{"role": "user", "content": prompt}], temperature=0.3)
                if resp.strip():
                    tailored_summary = resp.strip()
            except Exception as e:
                logger.warning("AI resume summary tailoring failed, using profile summary", error=str(e))

        resume_content = {
            "personal": profile.get("personal", {}),
            "summary": tailored_summary,
            "skills": profile.get("skills", []),
            "experience": profile.get("experience", []),
            "education": profile.get("education", []),
            "projects": profile.get("projects", []),
            "certifications": profile.get("certifications", []),
        }

        # PDF output location
        storage_dir = os.path.join(os.getcwd(), "storage", "resumes", str(user_id))
        pdf_path = os.path.join(storage_dir, f"resume_{job_id}.pdf")

        try:
            self.template.render_pdf(resume_content, pdf_path)
        except Exception as e:
            logger.error("Failed to render resume PDF", error=str(e))
            pdf_path = None

        now = datetime.now(timezone.utc)
        resume_doc = {
            "user_id": ObjectId(user_id),
            "job_id": ObjectId(job_id),
            "template": self.template.name,
            "content": resume_content,
            "pdf_path": pdf_path,
            "generated_at": now,
        }

        res = await db.resumes.insert_one(resume_doc)
        resume_doc["_id"] = res.inserted_id
        logger.info("Tailored resume generated", user_id=user_id, job_id=job_id, pdf=pdf_path)
        return resume_doc
