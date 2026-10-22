from datetime import datetime, timezone
import structlog
from app.db.client import get_db
from app.sources.static_urls import StaticUrlJobSource
from app.sources.company_ats import CompanyATSJobSource
from app.sources.linkedin import LinkedInJobSource
from app.sources.naukri import NaukriJobSource
from app.sources.base import RawJobData

logger = structlog.get_logger()


class JobFetcherAgent:
    """Discovers jobs from target company career portals, LinkedIn, and Naukri, deduplicates, and saves postings."""

    def __init__(self):
        self.static_source = StaticUrlJobSource()
        self.ats_source = CompanyATSJobSource()
        self.linkedin_source = LinkedInJobSource()
        self.naukri_source = NaukriJobSource()

    async def fetch_and_store_jobs(
        self,
        source: str = "all",
        custom_urls: list[str] | None = None,
        keywords: list[str] | None = None,
    ) -> list[dict]:
        db = get_db()
        all_raw_jobs: list[RawJobData] = []
        source_clean = (source or "all").lower().strip()

        if custom_urls:
            jobs = await self.static_source.fetch_jobs({"urls": custom_urls})
            all_raw_jobs.extend(jobs)
        else:
            # 1. Career Portals / Target ATS (Greenhouse, Lever, Ashby)
            if source_clean in ["career", "all"]:
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
                    for j in ats_jobs:
                        j.source = "career"
                    all_raw_jobs.extend(ats_jobs)

            # 2. LinkedIn Job Fetcher
            if source_clean in ["linkedin", "all"]:
                linkedin_jobs = await self.linkedin_source.fetch_jobs({
                    "keywords": keywords,
                    "location": "India",
                    "limit": 25,
                })
                for j in linkedin_jobs:
                    j.source = "linkedin"
                all_raw_jobs.extend(linkedin_jobs)

            # 3. Naukri Job Fetcher
            if source_clean in ["naukri", "all"]:
                naukri_jobs = await self.naukri_source.fetch_jobs({
                    "keyword": (keywords[0] if keywords else "software-engineer"),
                    "limit": 25,
                })
                for j in naukri_jobs:
                    j.source = "naukri"
                all_raw_jobs.extend(naukri_jobs)

            # 4. Check DB for custom job sources if configured
            if source_clean == "all":
                cursor_sources = db.job_sources.find({"is_active": True})
                async for doc in cursor_sources:
                    s_type = doc.get("type", "static_urls")
                    if s_type == "static_urls":
                        jobs = await self.static_source.fetch_jobs(doc.get("config", {}))
                        for j in jobs:
                            j.source = "career"
                        all_raw_jobs.extend(jobs)

        new_jobs = []
        now = datetime.now(timezone.utc)

        for raw in all_raw_jobs:
            content_hash = self.ats_source.get_content_hash(raw)
            # Check if job already exists by content_hash or external_id
            exists_query = {"$or": [{"content_hash": content_hash}, {"external_id": raw.external_id}]} if raw.external_id else {"content_hash": content_hash}
            exists = await db.jobs.find_one(exists_query)
            if exists:
                continue

            job_source = raw.source if raw.source in ["career", "linkedin", "naukri"] else "career"

            job_doc = {
                "source": job_source,
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

            try:
                res = await db.jobs.insert_one(job_doc)
                job_doc["_id"] = res.inserted_id
                new_jobs.append(job_doc)

                # Update company total_jobs_fetched counter if exists in db.companies
                await db.companies.update_one(
                    {"name": raw.company},
                    {"$inc": {"total_jobs_fetched": 1}, "$set": {"last_fetched_at": now}}
                )
            except Exception as e:
                # Catch duplicate key or concurrent write races cleanly
                logger.debug("Skip duplicate or conflicting job posting", title=raw.title, company=raw.company, error=str(e))
                continue

        logger.info("Job discovery completed", source=source_clean, discovered=len(new_jobs), total_scanned=len(all_raw_jobs))
        return new_jobs
