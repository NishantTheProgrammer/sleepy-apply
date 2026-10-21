from datetime import datetime, timezone
import structlog
from app.db.client import get_db
from app.sources.static_urls import StaticUrlJobSource
from app.sources.base import RawJobData
from app.models.job import Job

logger = structlog.get_logger()


class JobFetcherAgent:
    """Discovers jobs from configured sources, deduplicates, and saves new postings."""

    def __init__(self):
        self.static_source = StaticUrlJobSource()

    async def fetch_and_store_jobs(self, custom_urls: list[str] | None = None) -> list[dict]:
        db = get_db()
        sources_to_run: list[tuple[str, dict]] = []

        if custom_urls:
            sources_to_run.append(("static_urls", {"urls": custom_urls}))
        else:
            # Check DB for active job sources
            cursor = db.job_sources.find({"is_active": True})
            async for doc in cursor:
                sources_to_run.append((doc.get("type", "static_urls"), doc.get("config", {})))

        # Default fallback sample URLs if none configured
        if not sources_to_run:
            sources_to_run.append((
                "static_urls",
                {"urls": ["https://remoteok.com/api", "https://news.ycombinator.com/jobs"]}
            ))

        all_raw_jobs: list[RawJobData] = []
        for s_type, s_config in sources_to_run:
            if s_type == "static_urls":
                jobs = await self.static_source.fetch_jobs(s_config)
                all_raw_jobs.extend(jobs)

        new_jobs = []
        now = datetime.now(timezone.utc)

        for raw in all_raw_jobs:
            content_hash = self.static_source.get_content_hash(raw)
            # Check if job already exists
            exists = await db.jobs.find_one({"content_hash": content_hash})
            if exists:
                continue

            job_doc = {
                "source": "static_urls",
                "source_url": raw.source_url,
                "external_id": raw.external_id,
                "title": raw.title,
                "company": raw.company,
                "company_info": {"website": raw.company_website},
                "description": raw.description,
                "requirements": [],
                "responsibilities": [],
                "location": raw.location,
                "is_remote": raw.is_remote,
                "employment_type": raw.employment_type if raw.employment_type in ["full-time", "part-time", "contract", "internship"] else "full-time",
                "salary_range": {},
                "application_url": raw.application_url,
                "hr_contact": {},
                "required_skills": raw.required_skills,
                "is_active": True,
                "enriched": False,
                "discovered_at": now,
                "content_hash": content_hash,
            }

            res = await db.jobs.insert_one(job_doc)
            job_doc["_id"] = res.inserted_id
            new_jobs.append(job_doc)

        logger.info("Job discovery completed", discovered=len(new_jobs), total_scanned=len(all_raw_jobs))
        return new_jobs
