import json
import re
from datetime import datetime, timezone
import structlog
from bson import ObjectId
from app.db.client import get_db
from app.providers.factory import AIProviderFactory
from app.models.settings import UserSettings

logger = structlog.get_logger()

JOB_ENRICH_PROMPT = """Analyze this job posting description and extract the structured data in valid JSON format:
{
  "required_skills": ["string"],
  "responsibilities": ["string"],
  "requirements": ["string"],
  "is_remote": boolean,
  "employment_type": "full-time" | "part-time" | "contract" | "internship",
  "salary_min": number or null,
  "salary_max": number or null,
  "salary_currency": "USD" or null
}

Description:
"""


class JobEnrichmentAgent:
    """Enriches raw job postings with structured skill requirements and salary data."""

    async def enrich_job(self, job_id: str, user_settings: UserSettings | None = None) -> dict:
        db = get_db()
        job = await db.jobs.find_one({"_id": ObjectId(job_id)})
        if not job:
            return {}

        desc = job.get("description", "")
        enrichment_data = None

        if user_settings and desc:
            try:
                provider = AIProviderFactory.resolve(user_settings)
                prompt = JOB_ENRICH_PROMPT + desc[:5000]
                resp = await provider.complete([{"role": "user", "content": prompt}], temperature=0.1)
                match = re.search(r"\{[\s\S]*\}", resp)
                if match:
                    enrichment_data = json.loads(match.group(0))
            except Exception as e:
                logger.warning("AI job enrichment failed, falling back to heuristics", error=str(e))

        if not enrichment_data:
            enrichment_data = self._heuristic_enrich(desc)

        now = datetime.now(timezone.utc)
        update_fields = {
            "required_skills": enrichment_data.get("required_skills", job.get("required_skills", [])),
            "responsibilities": enrichment_data.get("responsibilities", []),
            "requirements": enrichment_data.get("requirements", []),
            "is_remote": enrichment_data.get("is_remote", job.get("is_remote", False)),
            "enriched": True,
            "enriched_at": now,
        }

        if enrichment_data.get("salary_min") or enrichment_data.get("salary_max"):
            update_fields["salary_range"] = {
                "min": enrichment_data.get("salary_min"),
                "max": enrichment_data.get("salary_max"),
                "currency": enrichment_data.get("salary_currency", "USD"),
            }

        await db.jobs.update_one({"_id": ObjectId(job_id)}, {"$set": update_fields})
        job.update(update_fields)
        logger.info("Job enriched successfully", job_id=job_id, skills_count=len(update_fields["required_skills"]))
        return job

    def _heuristic_enrich(self, desc: str) -> dict:
        common_skills = [
            "Python", "JavaScript", "TypeScript", "React", "Next.js", "Node.js",
            "Go", "Rust", "Java", "Docker", "Kubernetes", "AWS", "FastAPI",
            "MongoDB", "PostgreSQL", "SQL", "GraphQL", "Git", "Tailwind CSS",
            "Machine Learning", "PyTorch", "TensorFlow", "FastAPI"
        ]
        found = [s for s in common_skills if re.search(r"\b" + re.escape(s) + r"\b", desc, re.IGNORECASE)]
        is_remote = bool(re.search(r"\b(remote|work from home|wfh)\b", desc, re.IGNORECASE))

        # Detect salary range if present
        sal_match = re.search(r"\$(\d{2,3})[,\.]?(\d{3})?\s*-\s*\$?(\d{2,3})[,\.]?(\d{3})?", desc)
        sal_min, sal_max = None, None
        if sal_match:
            try:
                g1 = int(sal_match.group(1)) * (1000 if int(sal_match.group(1)) < 500 else 1)
                g3 = int(sal_match.group(3)) * (1000 if int(sal_match.group(3)) < 500 else 1)
                sal_min, sal_max = g1, g3
            except Exception:
                pass

        return {
            "required_skills": found,
            "responsibilities": [],
            "requirements": [],
            "is_remote": is_remote,
            "salary_min": sal_min,
            "salary_max": sal_max,
            "salary_currency": "USD" if sal_min else None,
        }
