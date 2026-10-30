from datetime import datetime, timezone
import structlog
from app.db.client import get_db
from app.sources.static_urls import StaticUrlJobSource
from app.sources.company_ats import CompanyATSJobSource
from app.sources.linkedin import LinkedInJobSource
from app.sources.naukri import NaukriJobSource
from app.sources.indeed import IndeedJobSource
from app.sources.playwright_crawler import PlaywrightJobCrawler
from app.sources.base import RawJobData
from app.pipeline.deduplicator import JobDeduplicator
from app.pipeline.normalizer import DelhiNCRJobNormalizer

logger = structlog.get_logger()


class JobFetcherAgent:
    """Discovers jobs from target company career portals (ATS APIs + Playwright), LinkedIn, Naukri, and Indeed; deduplicates and normalizes postings."""

    def __init__(self):
        self.static_source = StaticUrlJobSource()
        self.ats_source = CompanyATSJobSource()
        self.linkedin_source = LinkedInJobSource()
        self.naukri_source = NaukriJobSource()
        self.indeed_source = IndeedJobSource()
        self.playwright_crawler = PlaywrightJobCrawler()

    async def fetch_and_store_jobs(
        self,
        source: str = "all",
        custom_urls: list[str] | None = None,
        keywords: list[str] | None = None,
        delhi_ncr_only: bool = True,
    ) -> list[dict]:
        db = get_db()
        all_raw_jobs: list[RawJobData] = []
        source_clean = (source or "all").lower().strip()

        if custom_urls:
            jobs = await self.static_source.fetch_jobs({"urls": custom_urls})
            all_raw_jobs.extend(jobs)
        else:
            # 1. Career Portals / Target ATS (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Darwinbox, Keka)
            if source_clean in ["career", "all"]:
                active_companies = []
                custom_companies = []
                cursor = db.companies.find({"is_active": True})
                async for doc in cursor:
                    comp_info = {
                        "name": doc["name"],
                        "ats_type": doc.get("ats_type", "custom"),
                        "board_token": doc.get("board_token"),
                        "career_page": doc.get("career_page", ""),
                    }
                    if comp_info["ats_type"] == "custom" and comp_info["career_page"]:
                        custom_companies.append(comp_info)
                    else:
                        active_companies.append(comp_info)

                if active_companies:
                    ats_jobs = await self.ats_source.fetch_jobs({
                        "companies": active_companies,
                        "limit_per_company": 15,
                        "delhi_ncr_only": delhi_ncr_only,
                    })
                    for j in ats_jobs:
                        j.source = "career"
                    all_raw_jobs.extend(ats_jobs)

                # Fallback to Playwright crawler for custom / SPA career portals
                if custom_companies:
                    try:
                        pw_jobs = await self.playwright_crawler.fetch_jobs({
                            "companies": custom_companies[:5],  # polite batch limit for headless browsing
                            "delhi_ncr_only": delhi_ncr_only,
                            "limit_per_company": 10,
                        })
                        for j in pw_jobs:
                            j.source = "career"
                        all_raw_jobs.extend(pw_jobs)
                    except Exception as e:
                        logger.warning("Playwright custom crawler execution error", error=str(e))

            # 2. LinkedIn Job Fetcher (Targeting Delhi NCR tech hubs)
            if source_clean in ["linkedin", "all"]:
                linkedin_jobs = await self.linkedin_source.fetch_jobs({
                    "keywords": keywords,
                    "delhi_ncr_only": delhi_ncr_only,
                    "limit": 25,
                })
                for j in linkedin_jobs:
                    j.source = "linkedin"
                all_raw_jobs.extend(linkedin_jobs)

            # 3. Naukri Job Fetcher (Delhi & Noida XML Sitemaps)
            if source_clean in ["naukri", "all"]:
                naukri_jobs = await self.naukri_source.fetch_jobs({
                    "keyword": (keywords[0] if keywords else "software-engineer"),
                    "delhi_ncr_only": delhi_ncr_only,
                    "limit": 25,
                })
                for j in naukri_jobs:
                    j.source = "naukri"
                all_raw_jobs.extend(naukri_jobs)

            # 4. Indeed Job Fetcher (Delhi NCR RSS)
            if source_clean in ["indeed", "all"]:
                indeed_jobs = await self.indeed_source.fetch_jobs({
                    "keywords": keywords,
                    "delhi_ncr_only": delhi_ncr_only,
                    "limit": 25,
                })
                for j in indeed_jobs:
                    j.source = "indeed"
                all_raw_jobs.extend(indeed_jobs)

            # 5. Check DB for custom job sources if configured
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
            # Cross-Source Deduplication Key
            content_hash = JobDeduplicator.compute_raw_hash(raw)

            # Check if job already exists by content_hash or external_id
            exists_query = {"$or": [{"content_hash": content_hash}, {"external_id": raw.external_id}]} if raw.external_id else {"content_hash": content_hash}
            exists = await db.jobs.find_one(exists_query)
            if exists:
                continue

            # Process through Delhi NCR Job Normalizer
            norm = DelhiNCRJobNormalizer.normalize(raw)

            job_source = raw.source if raw.source in ["career", "linkedin", "naukri", "indeed"] else "career"

            job_doc = {
                "source": job_source,
                "source_url": norm["source_url"],
                "external_id": norm["external_id"],
                "title": norm["title"],
                "company": norm["company"],
                "company_info": {"website": raw.company_website or raw.source_url},
                "description": norm["description"],
                "requirements": [],
                "responsibilities": [],
                "location": norm["location"],
                "delhi_ncr_hub": norm["delhi_ncr_hub"],
                "is_delhi_ncr": norm["is_delhi_ncr"],
                "is_remote": norm["is_remote"],
                "work_model": norm["work_model"],
                "seniority": norm["seniority"],
                "employment_type": norm["employment_type"],
                "salary_range": norm["salary_range"],
                "application_url": norm["application_url"],
                "hr_contact": {},
                "required_skills": norm["required_skills"],
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
                logger.debug("Skip duplicate or conflicting job posting", title=raw.title, company=raw.company, error=str(e))
                continue

        logger.info("Job discovery completed", source=source_clean, discovered=len(new_jobs), total_scanned=len(all_raw_jobs), delhi_ncr_only=delhi_ncr_only)
        return new_jobs
