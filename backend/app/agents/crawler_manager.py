import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Any
import structlog

from app.db.client import get_db
from app.sources.ai_crawler import AICareerCrawlerAgent, CaptchaDetectedException
from app.pipeline.normalizer import DelhiNCRJobNormalizer
from app.pipeline.deduplicator import JobDeduplicator
from app.agents.job_matcher import JobMatcherAgent
from app.pipeline.role_search import get_unique_user_selected_roles
from app.core.system_logger import log_system_event

logger = structlog.get_logger()

# 10 Curated Top Tech Companies
TARGET_COMPANIES = [
    {
        "name": "MongoDB",
        "url": "https://www.mongodb.com/careers",
        "default_query": "Software Engineer",
    },
    {
        "name": "EXL Service",
        "url": "https://www.exlservice.com/careers",
        "default_query": "Lead Assistant Manager",
    },
    {
        "name": "BrowserStack",
        "url": "https://www.browserstack.com/careers",
        "default_query": "Software Engineer",
    },
    {
        "name": "OpenAI",
        "url": "https://openai.com/careers",
        "default_query": "Software Engineer",
    },
    {
        "name": "Anthropic",
        "url": "https://www.anthropic.com/careers",
        "default_query": "Engineer",
    },
    {
        "name": "Stripe",
        "url": "https://stripe.com/jobs",
        "default_query": "Software Engineer",
    },
    {
        "name": "Cloudflare",
        "url": "https://www.cloudflare.com/careers",
        "default_query": "Systems Engineer",
    },
    {
        "name": "Datadog",
        "url": "https://www.datadoghq.com/careers",
        "default_query": "Software Engineer",
    },
    {
        "name": "Uber",
        "url": "https://www.uber.com/in/en/careers/",
        "default_query": "Software Engineer",
    },
    {
        "name": "Atlassian",
        "url": "https://www.atlassian.com/company/careers",
        "default_query": "Software Engineer",
    },
]


class CrawlerManager:
    """Manages background batch runs of the AI browser crawler with real-time status reporting."""

    def __init__(self):
        self.state: dict[str, Any] = {
            "is_running": False,
            "current_company": None,
            "current_index": 0,
            "total_companies": len(TARGET_COMPANIES),
            "percent": 0,
            "status_message": "Ready",
            "jobs_discovered": 0,
            "jobs_saved": 0,
            "captchas_encountered": 0,
            "started_at": None,
            "finished_at": None,
            "history": [],
        }
        self._lock = asyncio.Lock()

    def get_status(self) -> dict[str, Any]:
        return dict(self.state)

    async def run_batch(
        self,
        companies: list[str] | None = None,
        headless: bool = False,
        limit_per_company: int = 5,
        slow_mo: int = 100,
    ) -> dict[str, Any]:
        async with self._lock:
            if self.state["is_running"]:
                return {"ok": False, "message": "Crawler is already running"}

            # Filter targets if requested
            targets = TARGET_COMPANIES
            if companies:
                c_set = {c.strip().lower() for c in companies if c.strip()}
                targets = [t for t in TARGET_COMPANIES if any(cs in t["name"].lower() for cs in c_set)]
                if not targets:
                    targets = TARGET_COMPANIES

            now_iso = datetime.now(timezone.utc).isoformat()
            self.state = {
                "is_running": True,
                "current_company": None,
                "current_index": 0,
                "total_companies": len(targets),
                "percent": 0,
                "status_message": f"Starting batch crawl across {len(targets)} companies...",
                "jobs_discovered": 0,
                "jobs_saved": 0,
                "captchas_encountered": 0,
                "started_at": now_iso,
                "finished_at": None,
                "history": [],
            }

        await log_system_event(
            level="INFO",
            category="crawler",
            message=f"Starting AI Browser batch crawl across {len(targets)} target companies.",
            details={"companies": [t["name"] for t in targets], "headless": headless},
        )

        try:
            db = get_db()
            matcher = JobMatcherAgent()
            users = await db.users.find({"is_active": True}).to_list(100)
            user_roles = await get_unique_user_selected_roles(db)
            primary_query = user_roles[0] if user_roles else None

            agent = AICareerCrawlerAgent()

            for idx, target in enumerate(targets, 1):
                comp_name = target["name"]
                career_url = target["url"]
                query_role = primary_query or target.get("default_query", "Software Engineer")

                percent = int(((idx - 1) / len(targets)) * 100)
                self.state["current_company"] = comp_name
                self.state["current_index"] = idx
                self.state["percent"] = percent
                self.state["status_message"] = f"Crawling [{comp_name}] ({idx}/{len(targets)})..."

                logger.info("Crawler starting company", company=comp_name, url=career_url, index=idx)

                try:
                    import os
                    is_in_docker = os.path.exists('/.dockerenv') or not os.environ.get('DISPLAY')
                    run_headless = True if is_in_docker else headless

                    jobs = await agent.crawl_career_portal(
                        company=comp_name,
                        start_url=career_url,
                        target_query=query_role,
                        headless=run_headless,
                        slow_mo=0 if run_headless else slow_mo,
                        limit=limit_per_company,
                    )

                    new_count = 0
                    for raw_job in jobs:
                        raw_job.source = "career-crawled"
                        content_hash = JobDeduplicator.compute_raw_hash(raw_job)
                        exists_query = (
                            {"$or": [{"content_hash": content_hash}, {"external_id": raw_job.external_id}]}
                            if raw_job.external_id
                            else {"content_hash": content_hash}
                        )
                        existing = await db.jobs.find_one(exists_query)

                        now = datetime.now(timezone.utc)
                        norm = DelhiNCRJobNormalizer.normalize(raw_job)
                        job_doc = {
                            "source": "career-crawled",
                            "source_url": norm["source_url"],
                            "external_id": norm["external_id"],
                            "title": norm["title"],
                            "company": norm["company"],
                            "company_info": {"website": raw_job.company_website or raw_job.source_url},
                            "description": norm["description"],
                            "requirements": getattr(raw_job, "requirements", []),
                            "responsibilities": getattr(raw_job, "responsibilities", []),
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
                            "posted_at": raw_job.posted_at or now,
                            "is_active": True,
                            "enriched": bool(norm.get("required_skills")),
                            "content_hash": content_hash,
                            "discovered_at": now,
                        }

                        if existing:
                            job_id = existing["_id"]
                            await db.jobs.update_one(
                                {"_id": job_id},
                                {
                                    "$set": {
                                        "source": "career-crawled",
                                        "is_active": True,
                                        "location": norm["location"],
                                        "description": norm["description"],
                                        "requirements": getattr(raw_job, "requirements", []),
                                        "responsibilities": getattr(raw_job, "responsibilities", []),
                                        "required_skills": norm["required_skills"],
                                        "enriched": bool(norm.get("required_skills")),
                                    }
                                },
                            )
                        else:
                            insert_res = await db.jobs.insert_one(job_doc)
                            job_id = insert_res.inserted_id
                            new_count += 1

                        # Score match
                        for u in users:
                            try:
                                await matcher.match_user_and_job(
                                    user_id=str(u["_id"]),
                                    job_id=str(job_id),
                                    use_ai_reasoning=False,
                                )
                            except Exception:
                                pass

                    self.state["jobs_discovered"] += len(jobs)
                    self.state["jobs_saved"] += new_count
                    self.state["history"].append({
                        "company": comp_name,
                        "status": "SUCCESS" if len(jobs) > 0 else "NO_JOBS",
                        "jobs_found": len(jobs),
                        "new_saved": new_count,
                    })

                except CaptchaDetectedException as ce:
                    self.state["captchas_encountered"] += 1
                    self.state["history"].append({
                        "company": comp_name,
                        "status": "CAPTCHA_ABORTED",
                        "reason": ce.captcha_type,
                        "jobs_found": 0,
                        "new_saved": 0,
                    })
                    logger.warning("Crawler aborted on CAPTCHA", company=comp_name, captcha=ce.captcha_type)

                except Exception as e:
                    self.state["history"].append({
                        "company": comp_name,
                        "status": "ERROR",
                        "reason": str(e)[:60],
                        "jobs_found": 0,
                        "new_saved": 0,
                    })
                    logger.error("Crawler error on company", company=comp_name, error=str(e))
                    await log_system_event(
                        level="ERROR",
                        category="crawler",
                        message=f"Error crawling {comp_name}: {str(e)[:120]}",
                        details={"company": comp_name, "error": str(e)},
                    )

            # Finalize
            self.state["is_running"] = False
            self.state["current_company"] = None
            self.state["percent"] = 100
            self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
            self.state["status_message"] = (
                f"Batch completed: {self.state['jobs_discovered']} jobs crawled "
                f"({self.state['jobs_saved']} new in DB, {self.state['captchas_encountered']} captchas aborted)."
            )

            await log_system_event(
                level="INFO",
                category="crawler",
                message=self.state["status_message"],
                details={
                    "total_discovered": self.state["jobs_discovered"],
                    "total_saved": self.state["jobs_saved"],
                    "captchas_encountered": self.state["captchas_encountered"],
                },
            )

        except Exception as e:
            self.state["is_running"] = False
            self.state["status_message"] = f"Fatal crawler error: {e}"
            logger.error("Fatal crawler loop failure", error=str(e))
            await log_system_event(
                level="CRITICAL",
                category="crawler",
                message=f"Crawler runner crashed: {str(e)}",
                details={"error": str(e)},
            )

        return self.get_status()


# Global singleton instance
crawler_manager = CrawlerManager()

