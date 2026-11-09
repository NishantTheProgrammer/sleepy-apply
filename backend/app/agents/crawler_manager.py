import asyncio
import os
import sys
import re
from datetime import datetime, timezone
from typing import Any
import structlog

from app.db.client import get_db
from app.sources.ai_crawler import AICareerCrawlerAgent, CaptchaDetectedException
from app.sources.company_ats import is_delhi_ncr_or_remote_job, is_relevant_tech_job
from app.pipeline.normalizer import DelhiNCRJobNormalizer
from app.pipeline.deduplicator import JobDeduplicator
from app.agents.job_matcher import JobMatcherAgent
from app.pipeline.role_search import get_unique_user_selected_roles
from app.core.system_logger import log_system_event

from app.scripts.crawl_delhi_ncr_companies import (
    load_companies,
    resolve_target_file,
    CrawlCheckpoint,
    DEFAULT_CHECKPOINT_FILE,
)

logger = structlog.get_logger()


def get_default_targets(
    companies: list[str] | None = None,
    grade: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Dynamically load verified Delhi NCR tech companies from JSON dataset."""
    try:
        resolved_file = resolve_target_file()
        grade_filters = [g.strip().upper() for g in grade.split(",")] if grade else None
        _, targets = load_companies(
            file_path=resolved_file,
            grade_filter=grade_filters,
            skip_placeholders=True,
            name_filter=companies,
        )
        if limit:
            targets = targets[:limit]
        return targets
    except Exception as e:
        logger.warning("Could not load Delhi NCR companies dataset, using fallback", error=str(e))
        return [
            {"rank": 1, "name": "Zomato", "url": "https://www.zomato.com/careers", "grade": "S"},
            {"rank": 2, "name": "Blinkit", "url": "https://blinkit.com/careers", "grade": "S"},
            {"rank": 3, "name": "Paytm", "url": "https://jobs.lever.co/paytm", "grade": "S"},
            {"rank": 4, "name": "Delhivery", "url": "https://www.delhivery.com/careers", "grade": "S"},
            {"rank": 5, "name": "Lenskart", "url": "https://hiring.lenskart.com/", "grade": "A"},
        ]


class CrawlerManager:
    """Manages background batch runs of the AI browser crawler with real-time status reporting."""

    def __init__(self):
        initial_targets = get_default_targets(limit=25)
        self.state: dict[str, Any] = {
            "is_running": False,
            "current_company": None,
            "current_index": 0,
            "total_companies": len(initial_targets),
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

            checkpoint = CrawlCheckpoint()
            targets = get_default_targets(companies=companies)

            now_iso = datetime.now(timezone.utc).isoformat()
            self.state = {
                "is_running": True,
                "current_company": None,
                "current_index": 0,
                "total_companies": len(targets),
                "percent": 0,
                "status_message": f"Starting batch crawl across {len(targets)} Delhi NCR companies...",
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
                rank = target.get("rank", idx)
                comp_name = target["name"]
                career_url = target["url"]

                if checkpoint.is_completed(rank) and not companies:
                    logger.info("Skipping already completed company from checkpoint", company=comp_name, rank=rank)
                    continue

                # Sanitize query: strip parenthetical qualifications like "(Node.js & React)" so ATS search bars don't fail
                if primary_query:
                    clean_role = re.sub(r'\(.*?\)', '', primary_query).strip()
                    query_role = clean_role if clean_role else "Software Engineer"
                else:
                    query_role = target.get("default_query", "Software Engineer")

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
                        delhi_ncr_only=True,
                        limit=limit_per_company,
                    )

                    new_count = 0
                    for raw_job in jobs:
                        # Strictly enforce that title is a technical / software engineering role (no sales, HR, marketing, warehouse)
                        if not is_relevant_tech_job(raw_job.title, query_role):
                            logger.info(
                                "Skipping non-relevant / non-tech job",
                                company=comp_name,
                                title=raw_job.title,
                            )
                            continue

                        # Strictly enforce Delhi NCR (Gurgaon, Noida, Delhi, etc.) or Remote
                        if not is_delhi_ncr_or_remote_job(raw_job.location, raw_job.title, raw_job.description or ""):
                            logger.info(
                                "Skipping non-Delhi-NCR / non-Remote job",
                                company=comp_name,
                                title=raw_job.title,
                                location=raw_job.location,
                            )
                            continue

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
                    status_str = "SUCCESS" if len(jobs) > 0 else "NO_JOBS"
                    self.state["history"].append({
                        "company": comp_name,
                        "status": status_str,
                        "jobs_found": len(jobs),
                        "new_saved": new_count,
                    })
                    checkpoint.record_company(
                        rank=rank,
                        company_name=comp_name,
                        url=career_url,
                        status=status_str,
                        jobs_found=len(jobs),
                        jobs_new=new_count,
                    )

                except CaptchaDetectedException as ce:
                    self.state["captchas_encountered"] += 1
                    self.state["history"].append({
                        "company": comp_name,
                        "status": "CAPTCHA_ABORTED",
                        "reason": ce.captcha_type,
                        "jobs_found": 0,
                        "new_saved": 0,
                    })
                    checkpoint.record_company(
                        rank=rank,
                        company_name=comp_name,
                        url=career_url,
                        status=f"CAPTCHA: {ce.captcha_type[:15]}",
                        jobs_found=0,
                        jobs_new=0,
                        error_msg=str(ce),
                    )
                    logger.warning("Crawler aborted on CAPTCHA", company=comp_name, captcha=ce.captcha_type)

                except Exception as e:
                    self.state["history"].append({
                        "company": comp_name,
                        "status": "ERROR",
                        "reason": str(e)[:60],
                        "jobs_found": 0,
                        "new_saved": 0,
                    })
                    checkpoint.record_company(
                        rank=rank,
                        company_name=comp_name,
                        url=career_url,
                        status=f"ERROR: {str(e)[:30]}",
                        jobs_found=0,
                        jobs_new=0,
                        error_msg=str(e),
                    )
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

