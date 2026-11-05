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
from app.pipeline.role_search import expand_role_to_search_keywords

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

        # Resolve role keywords: prioritize passed user keywords; fallback to all active users' selected roles in DB
        active_roles: list[str] = []
        if keywords:
            if isinstance(keywords, str):
                keywords = [keywords]
            active_roles = list(keywords)
        else:
            try:
                cursor = db.profiles.find(
                    {
                        "$or": [
                            {"target_role": {"$exists": True, "$nin": [None, ""]}},
                            {"job_preferences.jobTitles": {"$exists": True, "$nin": [None, []]}},
                            {"jobPreferences.jobTitles": {"$exists": True, "$nin": [None, []]}},
                            {"suggested_roles": {"$exists": True, "$nin": [None, []]}},
                        ]
                    },
                    {
                        "target_role": 1,
                        "job_preferences.jobTitles": 1,
                        "jobPreferences.jobTitles": 1,
                        "suggested_roles": 1,
                    },
                )
                async for p in cursor:
                    tr = p.get("target_role")
                    if tr and isinstance(tr, str) and tr.strip():
                        active_roles.append(tr.strip())
                    for t in (p.get("job_preferences", {}).get("jobTitles") or []):
                        if t and isinstance(t, str) and t.strip():
                            active_roles.append(t.strip())
                    for t in (p.get("jobPreferences", {}).get("jobTitles") or []):
                        if t and isinstance(t, str) and t.strip():
                            active_roles.append(t.strip())
                    for t in (p.get("suggested_roles") or []):
                        if t and isinstance(t, str) and t.strip():
                            active_roles.append(t.strip())
            except Exception as e:
                logger.warning("Could not query active user roles for job discovery", error=str(e))

        resolved_keywords = expand_role_to_search_keywords(active_roles) if active_roles else None
        if resolved_keywords:
            logger.info("Targeting user-selected roles for job fetching", keywords=resolved_keywords[:8], count=len(resolved_keywords))

        if custom_urls:
            try:
                jobs = await self.static_source.fetch_jobs({"urls": custom_urls})
                all_raw_jobs.extend(jobs)
            except Exception as e:
                logger.error("Static URL fetch error", error=str(e))
        else:
            # 1. Career Portals / Target ATS (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Darwinbox, Keka)
            if source_clean in ["career", "all"]:
                try:
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
                except Exception as e:
                    logger.error("Career ATS source error", error=str(e))

            # 2. LinkedIn Job Fetcher (Targeting Delhi NCR tech hubs for user-selected roles)
            if source_clean in ["linkedin", "all"]:
                try:
                    linkedin_jobs = await self.linkedin_source.fetch_jobs({
                        "keywords": resolved_keywords,
                        "delhi_ncr_only": delhi_ncr_only,
                        "max_age_days": 14,
                        "limit": 25,
                    })
                    for j in linkedin_jobs:
                        j.source = "linkedin"
                    all_raw_jobs.extend(linkedin_jobs)
                except Exception as e:
                    logger.error("LinkedIn source error", error=str(e))

            # 3. Naukri Job Fetcher (Delhi & Noida XML Sitemaps for user-selected roles)
            if source_clean in ["naukri", "all"]:
                try:
                    naukri_jobs = await self.naukri_source.fetch_jobs({
                        "keywords": resolved_keywords,
                        "delhi_ncr_only": delhi_ncr_only,
                        "max_age_days": 14,
                        "limit": 25,
                    })
                    for j in naukri_jobs:
                        j.source = "naukri"
                    all_raw_jobs.extend(naukri_jobs)
                except Exception as e:
                    logger.error("Naukri source error", error=str(e))

            # 4. Indeed Job Fetcher (Delhi NCR RSS for user-selected roles)
            if source_clean in ["indeed", "all"]:
                try:
                    indeed_jobs = await self.indeed_source.fetch_jobs({
                        "keywords": resolved_keywords,
                        "delhi_ncr_only": delhi_ncr_only,
                        "max_age_days": 14,
                        "limit": 25,
                    })
                    for j in indeed_jobs:
                        j.source = "indeed"
                    all_raw_jobs.extend(indeed_jobs)
                except Exception as e:
                    logger.error("Indeed source error", error=str(e))

            # 5. Check DB for custom job sources if configured
            if source_clean == "all":
                try:
                    cursor_sources = db.job_sources.find({"is_active": True})
                    async for doc in cursor_sources:
                        s_type = doc.get("type", "static_urls")
                        if s_type == "static_urls":
                            jobs = await self.static_source.fetch_jobs(doc.get("config", {}))
                            for j in jobs:
                                j.source = "career"
                            all_raw_jobs.extend(jobs)
                except Exception as e:
                    logger.error("Custom DB sources error", error=str(e))

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
                "posted_at": norm.get("posted_at") or raw.posted_at or now,
                "posted_at_raw": norm.get("posted_at_raw") or raw.posted_at_raw,
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
