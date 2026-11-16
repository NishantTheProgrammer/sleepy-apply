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
from app.pipeline.role_search import get_unique_user_selected_roles, format_roles_for_search_query
from app.core.retention import is_older_than_retention
from app.agents.hr_contact_finder import hr_contact_finder

logger = structlog.get_logger()


class JobFetcherAgent:
    """Discovers jobs from target company career portals (ATS APIs + Playwright), LinkedIn, Naukri, and Indeed; deduplicates and normalizes postings."""

    def __init__(self):
        self.static_source = StaticUrlJobSource()
        self.ats_source = CompanyATSJobSource()
        self.linkedin_source = LinkedInJobSource()
        self.naukri_source = NaukriJobSource()
        self.indeed_source = IndeedJobSource()
        self.playwright_crawler = PlaywrightJobCrawler(headless=True)

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

        # Resolve unique roles selected by users from db.profiles
        if keywords:
            user_roles = [keywords] if isinstance(keywords, str) else list(keywords)
        else:
            user_roles = await get_unique_user_selected_roles(db)

        resolved_keywords = format_roles_for_search_query(user_roles) if user_roles else None
        if resolved_keywords:
            logger.info("Targeting user-selected roles for job fetching", count=len(resolved_keywords), sample=resolved_keywords[:6])
        else:
            logger.info("No user-selected roles found in profiles; skipping role-based crawl")

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
                        raw_type = doc.get("ats_type")
                        ats_clean = (raw_type if raw_type else "custom").lower().strip()
                        comp_info = {
                            "name": doc["name"],
                            "ats_type": ats_clean,
                            "board_token": doc.get("board_token"),
                            "career_page": doc.get("career_page", ""),
                        }
                        if comp_info["ats_type"] in ["greenhouse", "lever", "ashby", "smartrecruiters", "workday", "darwinbox", "keka"]:
                            active_companies.append(comp_info)
                        elif comp_info["career_page"]:
                            custom_companies.append(comp_info)

                    if active_companies:
                        ats_jobs = await self.ats_source.fetch_jobs({
                            "companies": active_companies,
                            "limit_per_company": 25,
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
                                "headless": True,
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
                        "limit": 50,
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
                        "limit": 50,
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
            if is_older_than_retention(getattr(raw, "posted_at", None)):
                logger.debug("Skipping job older than 2 months", title=raw.title, company=raw.company, posted_at=str(raw.posted_at))
                continue

            # Cross-Source Deduplication Key
            content_hash = JobDeduplicator.compute_raw_hash(raw)

            # Check if job already exists by content_hash or external_id
            exists_query = {"$or": [{"content_hash": content_hash}, {"external_id": raw.external_id}]} if raw.external_id else {"content_hash": content_hash}
            exists = await db.jobs.find_one(exists_query)
            if exists:
                continue

            # Process through Delhi NCR Job Normalizer
            norm = DelhiNCRJobNormalizer.normalize(raw)

            job_source = raw.source if raw.source in ["career", "career-crawled", "linkedin", "naukri", "indeed"] else "career"

            # Extract or synthesize HR contact info for the position
            hr_contact = hr_contact_finder.extract_from_text(
                f"{norm['title']}\n{norm['company']}\n{norm['description']}",
                company=norm["company"],
                title=norm["title"],
            )
            if not hr_contact.get("email") and not hr_contact.get("phone"):
                hr_contact = hr_contact_finder.synthesize_company_contact(
                    norm["company"],
                    website=raw.company_website or raw.source_url,
                    source_url=norm["source_url"],
                )

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
                "hr_contact": hr_contact,
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


async def parse_job_details_from_url(url: str) -> dict:
    """Parse real title, company, and location from any job URL (LinkedIn, Greenhouse, Lever, Ashby, or HTML page)."""
    import re
    import html as html_lib
    import httpx
    clean_url = url.strip("<>.,;()\"' ")
    title = "Software Engineer"
    company = "Company"
    location = "India / Remote"

    # 1. Parse LinkedIn Job view URL slug
    li_match = re.search(r"/jobs/view/([a-zA-Z0-9\-]+)(?:-\d+)?", clean_url)
    if li_match:
        slug = li_match.group(1)
        if "-at-" in slug:
            t_part, c_part = slug.split("-at-", 1)
            c_part = re.sub(r"-\d+$", "", c_part)
            title = t_part.replace("-", " ").title()
            company = c_part.replace("-", " ").title()
        else:
            title = slug.replace("-", " ").title()

    # 2. Parse Greenhouse URL
    gh_match = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", clean_url)
    if gh_match:
        company = gh_match.group(1).replace("-", " ").title()

    # 3. Parse Lever URL
    lever_match = re.search(r"lever\.co/([^/]+)/([a-zA-Z0-9\-]+)", clean_url)
    if lever_match:
        company = lever_match.group(1).replace("-", " ").title()

    # 4. Parse Ashby URL
    ashby_match = re.search(r"jobs\.ashbyhq\.com/([^/]+)/([a-zA-Z0-9\-]+)", clean_url)
    if ashby_match:
        company = ashby_match.group(1).replace("-", " ").title()

    # 5. Live HTML fetch attempt
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=5.0) as client:
            resp = await client.get(clean_url)
            if resp.status_code == 200:
                html_text = resp.text
                og_t = re.search(r'<meta[^>]+property=[\'"]og:title[\'"][^>]+content=[\'"](.*?)[\'"]', html_text, re.IGNORECASE)
                og_c = re.search(r'<meta[^>]+property=[\'"]og:site_name[\'"][^>]+content=[\'"](.*?)[\'"]', html_text, re.IGNORECASE)
                page_t = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE)
                raw_title = (og_t.group(1) if og_t else "") or (page_t.group(1) if page_t else "")
                if raw_title:
                    clean_t = html_lib.unescape(raw_title).strip()
                    if " at " in clean_t:
                        parts = clean_t.split(" at ", 1)
                        title = parts[0].strip()
                        comp_candidate = re.split(r"[|\-–]", parts[1])[0].strip()
                        if comp_candidate and len(comp_candidate) < 40:
                            company = comp_candidate
                    elif " | " in clean_t or " - " in clean_t:
                        parts = re.split(r"\s*[|\-–]\s*", clean_t)
                        if len(parts) >= 2:
                            title = parts[0].strip()
                            company = parts[1].strip()
                if og_c and (not company or company == "Company"):
                    company = og_c.group(1).strip()
    except Exception:
        pass

    return {
        "title": title,
        "company": company,
        "source_url": clean_url,
        "application_url": clean_url,
        "description": f"Position for {title} at {company}. Direct application link: {clean_url}",
        "location": location,
    }
