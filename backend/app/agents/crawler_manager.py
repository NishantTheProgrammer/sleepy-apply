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
    DEFAULT_CHECKPOINT_ID,
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
        initial_targets = get_default_targets()
        self.state: dict[str, Any] = {
            "is_running": False,
            "is_paused": False,
            "current_company": None,
            "active_companies": [],
            "concurrency": 3,
            "current_index": 0,
            "total_companies": len(initial_targets),
            "percent": 0,
            "status_message": "Ready",
            "jobs_discovered": 0,
            "jobs_saved": 0,
            "captchas_encountered": 0,
            "started_at": None,
            "finished_at": None,
            "paused_at": None,
            "breakpoint": None,
            "history": [],
        }
        self._lock = asyncio.Lock()
        self._pause_requested = False

    def get_status(self) -> dict[str, Any]:
        return dict(self.state)

    async def pause(self) -> dict[str, Any]:
        """Request active crawler to pause and record breakpoint with exploration summary."""
        if not self.state.get("is_running"):
            return {
                "ok": False,
                "message": "Crawler is not currently running.",
                "status": self.get_status(),
            }

        self._pause_requested = True
        self.state["is_paused"] = True
        self.state["paused_at"] = datetime.now(timezone.utc).isoformat()
        self.state["status_message"] = "Pausing crawler at current breakpoint..."

        checkpoint = CrawlCheckpoint()
        await checkpoint.load()
        completed_ranks = checkpoint.data.get("completed_ranks", [])
        last_rank = max(completed_ranks) if completed_ranks else self.state.get("current_index", 0)

        targets = get_default_targets()
        last_company = self.state.get("current_company") or "Unknown"
        next_company = ""
        for t in targets:
            if t.get("rank") == last_rank:
                last_company = t.get("name", last_company)
            elif t.get("rank") == last_rank + 1:
                next_company = t.get("name", "")

        completed_count = len(completed_ranks) or self.state.get("current_index", 0)
        breakpoint_info = {
            "rank": last_rank,
            "company": last_company,
            "completed_count": completed_count,
            "total_companies": len(targets),
            "jobs_discovered": self.state.get("jobs_discovered", 0),
            "jobs_saved": self.state.get("jobs_saved", 0),
            "captchas_encountered": self.state.get("captchas_encountered", 0),
            "next_company": next_company,
        }
        self.state["breakpoint"] = breakpoint_info

        # Trigger message to Discord #admin channel
        try:
            from app.agents.discord_bot import DiscordAgent
            discord = DiscordAgent()
            await discord.notify_admin_crawler_paused(
                breakpoint_rank=last_rank,
                breakpoint_company=last_company,
                completed_count=completed_count,
                total_companies=len(targets),
                jobs_discovered=self.state.get("jobs_discovered", 0),
                jobs_saved=self.state.get("jobs_saved", 0),
                captchas_encountered=self.state.get("captchas_encountered", 0),
                next_company=next_company,
            )
        except Exception as e:
            logger.warning("Failed to dispatch crawler pause notification to Discord", error=str(e))

        await log_system_event(
            level="WARNING",
            category="crawler",
            message=f"AI Browser Crawler paused by admin at breakpoint Rank {last_rank} ({last_company}). Explored {completed_count}/{len(targets)} companies.",
            details=breakpoint_info,
        )

        return {
            "ok": True,
            "message": (
                f"⏸️ Crawler paused. Explored {completed_count}/{len(targets)} "
                f"companies till now (Breakpoint: Rank {last_rank} - {last_company}). "
                f"{breakpoint_info['jobs_saved']} new jobs saved."
            ),
            "breakpoint": breakpoint_info,
            "status": self.get_status(),
        }

    async def run_batch(
        self,
        companies: list[str] | None = None,
        headless: bool = False,
        limit_per_company: int = 5,
        slow_mo: int = 100,
        concurrency: int = 3,
    ) -> dict[str, Any]:
        async with self._lock:
            if self.state["is_running"]:
                return {"ok": False, "message": "Crawler is already running"}

            self._pause_requested = False
            checkpoint = CrawlCheckpoint()
            await checkpoint.load()
            targets = get_default_targets(companies=companies)

            # Auto-reset if all targets were already completed in checkpoint (enables clean restart of full list)
            if not companies and len(checkpoint.data.get("completed_ranks", [])) >= len(targets):
                logger.info("All target companies already completed in checkpoint; auto-resetting for a fresh run.")
                await checkpoint.reset()

            concurrency = max(1, min(concurrency, 6))

            now_iso = datetime.now(timezone.utc).isoformat()
            already_done = len(checkpoint.data.get("completed_ranks", [])) if not companies else 0
            initial_pct = int((already_done / max(1, len(targets))) * 100)

            self.state = {
                "is_running": True,
                "is_paused": False,
                "current_company": None,
                "active_companies": [],
                "concurrency": concurrency,
                "current_index": already_done,
                "total_companies": len(targets),
                "percent": min(100, initial_pct),
                "status_message": f"Starting {concurrency}x parallel crawl across {len(targets)} companies...",
                "jobs_discovered": 0,
                "jobs_saved": 0,
                "captchas_encountered": 0,
                "started_at": now_iso,
                "finished_at": None,
                "paused_at": None,
                "breakpoint": None,
                "history": [],
            }

        await log_system_event(
            level="INFO",
            category="crawler",
            message=f"Starting AI Browser parallel crawl (concurrency={concurrency}) across {len(targets)} target companies.",
            details={"companies_count": len(targets), "concurrency": concurrency, "headless": headless},
        )

        try:
            db = get_db()
            matcher = JobMatcherAgent()
            users = await db.users.find({"is_active": True}).to_list(100)
            user_roles = await get_unique_user_selected_roles(db)
            primary_query = user_roles[0] if user_roles else None

            # Filter targets: if not a targeted companies list, skip already completed ranks
            pending_targets = [
                (idx, t)
                for idx, t in enumerate(targets, 1)
                if companies or not checkpoint.is_completed(t.get("rank", idx))
            ]

            if not pending_targets:
                self.state["is_running"] = False
                self.state["status_message"] = f"All {len(targets)} companies already completed in checkpoint."
                self.state["percent"] = 100
                return self.get_status()

            sem = asyncio.Semaphore(concurrency)
            state_lock = asyncio.Lock()
            checkpoint_lock = asyncio.Lock()
            active_companies: set[str] = set()
            completed_count = already_done

            async def crawl_worker(idx: int, target: dict[str, Any]):
                nonlocal completed_count
                if self._pause_requested:
                    return

                rank = target.get("rank", idx)
                comp_name = target["name"]
                career_url = target["url"]

                async with sem:
                    if self._pause_requested:
                        return
                    async with state_lock:
                        active_companies.add(comp_name)
                        self.state["active_companies"] = sorted(list(active_companies))
                        self.state["current_company"] = comp_name
                        self.state["status_message"] = (
                            f"Crawling {len(active_companies)} companies in parallel "
                            f"({completed_count}/{len(targets)} done)... [{', '.join(sorted(list(active_companies))[:3])}]"
                        )

                    logger.info("Crawler starting company", company=comp_name, url=career_url, rank=rank)
                    jobs = []
                    new_count = 0
                    status_str = "SUCCESS"
                    err_msg = None

                    try:
                        # Sanitize query
                        if primary_query:
                            clean_role = re.sub(r'\(.*?\)', '', primary_query).strip()
                            query_role = clean_role if clean_role else "Software Engineer"
                        else:
                            query_role = target.get("default_query", "Software Engineer")

                        is_in_docker = os.path.exists('/.dockerenv') or not os.environ.get('DISPLAY')
                        run_headless = True if is_in_docker else headless

                        worker_agent = AICareerCrawlerAgent()
                        jobs = await worker_agent.crawl_career_portal(
                            company=comp_name,
                            start_url=career_url,
                            target_query=query_role,
                            headless=run_headless,
                            slow_mo=0 if run_headless else slow_mo,
                            delhi_ncr_only=True,
                            limit=limit_per_company,
                        )

                        for raw_job in jobs:
                            if not is_relevant_tech_job(raw_job.title, query_role):
                                logger.debug("Skipping non-relevant non-tech job", company=comp_name, title=raw_job.title)
                                continue

                            if not is_delhi_ncr_or_remote_job(raw_job.location, raw_job.title, raw_job.description or ""):
                                logger.debug("Skipping non-Delhi-NCR job", company=comp_name, title=raw_job.title, loc=raw_job.location)
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

                            for u in users:
                                try:
                                    await matcher.match_user_and_job(
                                        user_id=str(u["_id"]),
                                        job_id=str(job_id),
                                        use_ai_reasoning=False,
                                    )
                                except Exception:
                                    pass

                        status_str = "SUCCESS" if len(jobs) > 0 else "NO_JOBS"

                    except CaptchaDetectedException as ce:
                        status_str = f"CAPTCHA: {ce.captcha_type[:15]}"
                        err_msg = str(ce)
                        async with state_lock:
                            self.state["captchas_encountered"] += 1
                        logger.warning("Crawler hit CAPTCHA", company=comp_name, captcha=ce.captcha_type)

                    except Exception as e:
                        status_str = f"ERROR: {str(e)[:30]}"
                        err_msg = str(e)
                        logger.error("Crawler error on company", company=comp_name, error=str(e))
                    finally:
                        async with checkpoint_lock:
                            await checkpoint.record_company(
                                rank=rank,
                                company_name=comp_name,
                                url=career_url,
                                status=status_str,
                                jobs_found=len(jobs),
                                jobs_new=new_count,
                                error_msg=err_msg,
                            )

                        async with state_lock:
                            active_companies.discard(comp_name)
                            completed_count += 1
                            self.state["active_companies"] = sorted(list(active_companies))
                            self.state["jobs_discovered"] += len(jobs)
                            self.state["jobs_saved"] += new_count
                            self.state["current_index"] = completed_count
                            pct = int((completed_count / max(1, len(targets))) * 100)
                            self.state["percent"] = min(100, pct)
                            if active_companies:
                                self.state["status_message"] = (
                                    f"Crawling {len(active_companies)} in parallel ({completed_count}/{len(targets)} completed)... "
                                    f"[{', '.join(sorted(list(active_companies))[:3])}]"
                                )
                            else:
                                self.state["status_message"] = f"Processed {completed_count}/{len(targets)} companies."
                            self.state["history"].append({
                                "rank": rank,
                                "company": comp_name,
                                "jobs": len(jobs),
                                "new_saved": new_count,
                                "status": status_str,
                            })

            # Launch parallel worker tasks with graceful exception handling
            tasks = [crawl_worker(idx, t) for idx, t in pending_targets]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Finalize batch state
            self.state["is_running"] = False
            self.state["current_company"] = None
            self.state["active_companies"] = []

            if self._pause_requested:
                self.state["is_paused"] = True
                return self.get_status()

            self.state["percent"] = 100
            self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
            self.state["status_message"] = (
                f"Batch completed: {self.state['jobs_discovered']} jobs crawled "
                f"({self.state['jobs_saved']} new in DB, {self.state['captchas_encountered']} captchas encountered)."
            )

            await log_system_event(
                level="INFO",
                category="crawler",
                message=self.state["status_message"],
                details={
                    "total_discovered": self.state["jobs_discovered"],
                    "total_saved": self.state["jobs_saved"],
                    "captchas_encountered": self.state["captchas_encountered"],
                    "concurrency": concurrency,
                },
            )

            # Broadcast crawl summary to Discord #admin channel
            try:
                from app.agents.discord_bot import DiscordAgent
                discord_agent = DiscordAgent()
                await discord_agent.notify_admin_crawl(
                    crawled_count=self.state["jobs_discovered"],
                    source_breakdown={
                        "Delhi NCR ATS": self.state["jobs_discovered"],
                        "New Saved": self.state["jobs_saved"],
                        "Captchas": self.state["captchas_encountered"],
                    },
                    checkpoint_summary=f"Processed {len(self.state['history'])} target companies.",
                )
            except Exception as d_err:
                logger.warning("Discord admin crawl notification failed", error=str(d_err))

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

