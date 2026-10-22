from datetime import datetime, timezone
import structlog
from app.db.client import get_db
from app.sources.static_urls import StaticUrlJobSource
from app.sources.company_ats import CompanyATSJobSource
from app.sources.base import RawJobData
from app.db.seed_jobs import seed_jobs_collection

logger = structlog.get_logger()


class JobFetcherAgent:
    """Discovers jobs from target companies and configured sources, deduplicates, and saves new postings."""

    def __init__(self):
        self.static_source = StaticUrlJobSource()
        self.ats_source = CompanyATSJobSource()

    async def fetch_and_store_jobs(self, custom_urls: list[str] | None = None) -> list[dict]:
        db = get_db()
        all_raw_jobs: list[RawJobData] = []

        if custom_urls:
            jobs = await self.static_source.fetch_jobs({"urls": custom_urls})
            all_raw_jobs.extend(jobs)
        else:
            # 1. Fetch from verified target companies in db.companies
            active_companies = []
            cursor = db.companies.find({"is_active": True})
            async for doc in cursor:
                active_companies.append({
                    "name": doc["name"],
                    "ats_type": doc.get("ats_type", "custom"),
                    "board_token": doc.get("board_token"),
                    "career_page": doc.get("career_page", ""),
                })

            if active_companies:
                ats_jobs = await self.ats_source.fetch_jobs({
                    "companies": active_companies,
                    "limit_per_company": 10,
                })
                all_raw_jobs.extend(ats_jobs)

            # 2. Check DB for custom job sources if configured
            cursor_sources = db.job_sources.find({"is_active": True})
            async for doc in cursor_sources:
                s_type = doc.get("type", "static_urls")
                if s_type == "static_urls":
                    jobs = await self.static_source.fetch_jobs(doc.get("config", {}))
                    all_raw_jobs.extend(jobs)

        new_jobs = []
        now = datetime.now(timezone.utc)

        for raw in all_raw_jobs:
            content_hash = self.ats_source.get_content_hash(raw)
            # Check if job already exists
            exists = await db.jobs.find_one({"content_hash": content_hash})
            if exists:
                continue

            job_doc = {
                "source": "company_ats",
                "source_url": raw.source_url,
                "external_id": raw.external_id,
                "title": raw.title,
                "company": raw.company,
                "company_info": {"website": raw.company_website or raw.source_url},
                "description": raw.description,
                "requirements": [],
                "responsibilities": [],
                "location": raw.location,
                "is_remote": raw.is_remote,
                "employment_type": raw.employment_type if raw.employment_type in ["full-time", "part-time", "contract", "internship"] else "full-time",
                "salary_range": {},
                "application_url": raw.application_url or raw.source_url,
                "hr_contact": {},
                "required_skills": raw.required_skills,
                "is_active": True,
                "enriched": True,
                "discovered_at": now,
                "content_hash": content_hash,
            }

            res = await db.jobs.insert_one(job_doc)
            job_doc["_id"] = res.inserted_id
            new_jobs.append(job_doc)

            # Update company total_jobs_fetched counter
            await db.companies.update_one(
                {"name": raw.company},
                {"$inc": {"total_jobs_fetched": 1}, "$set": {"last_fetched_at": now}}
            )

        logger.info("Job discovery completed", discovered=len(new_jobs), total_scanned=len(all_raw_jobs))
        return new_jobs
