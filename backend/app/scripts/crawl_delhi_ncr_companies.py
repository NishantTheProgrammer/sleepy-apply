#!/usr/bin/env python3
"""
Resumable Delhi NCR Tech Career Crawler.
Crawls career portals loaded from 'top_500_delhi_ncr_tech.json' using the AI Browser Agent,
tags discovered postings as 'career-crawled', persists them to MongoDB (db.jobs),
and computes explainable candidate compatibility scores.

Features:
- Resumable: Maintains persistent checkpoint state in .crawl_checkpoint_delhi_ncr.json.
- Graceful interruption (Ctrl+C): Saves progress immediately so re-running resumes from the exact next company.
- Automatic filtering: Skips placeholder companies and focuses on verified career portals.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Any
import structlog

# Ensure backend root is in sys.path
backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.db.client import connect_db, get_db
from app.sources.ai_crawler import AICareerCrawlerAgent, CaptchaDetectedException
from app.sources.company_ats import is_delhi_ncr_or_remote_job, is_relevant_tech_job
from app.core.system_logger import log_system_event
from app.pipeline.normalizer import DelhiNCRJobNormalizer
from app.pipeline.deduplicator import JobDeduplicator
from app.agents.job_matcher import JobMatcherAgent
from app.pipeline.role_search import get_unique_user_selected_roles

logger = structlog.get_logger()

DEFAULT_JSON_PATHS = [
    os.path.abspath(os.path.join(backend_root, "delhi_ncr_tech_companies.json")),
    os.path.abspath(os.path.join(backend_root, "..", "delhi_ncr_tech_companies.json")),
    os.path.abspath(os.path.join(os.getcwd(), "delhi_ncr_tech_companies.json")),
    os.path.abspath("/Users/nishant/Desktop/delhi_ncr_tech_companies.json"),
    os.path.abspath(os.path.join(backend_root, "top_500_delhi_ncr_tech.json")),
    os.path.abspath(os.path.join(backend_root, "..", "top_500_delhi_ncr_tech.json")),
    os.path.abspath(os.path.join(os.getcwd(), "top_500_delhi_ncr_tech.json")),
    os.path.abspath(os.path.join(backend_root, "top_500_tech_companies_india.json")),
    os.path.abspath(os.path.join(backend_root, "..", "top_500_tech_companies_india.json")),
]

DEFAULT_CHECKPOINT_ID = "delhi_ncr_crawler"


# ---------------------------------------------------------------------------
# Checkpoint & State Management (MongoDB db.crawler_checkpoints)
# ---------------------------------------------------------------------------

class CrawlCheckpoint:
    """MongoDB-backed persistent checkpoint tracking crawled companies, jobs found, and failures."""

    def __init__(self, doc_id: str = DEFAULT_CHECKPOINT_ID):
        self.doc_id = doc_id
        self.data: dict[str, Any] = {
            "_id": self.doc_id,
            "crawl_date": None,
            "source_file": "",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "completed_ranks": [],
            "completed_companies": [],
            "stats": {
                "total_crawled": 0,
                "total_jobs_discovered": 0,
                "total_jobs_saved": 0,
                "captchas_encountered": 0,
                "errors_encountered": 0,
            },
            "history": [],
        }

    def should_reset_daily(self) -> bool:
        """Returns True if the loaded checkpoint belongs to a previous calendar date."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        stored_date = self.data.get("crawl_date")
        if not stored_date:
            ts = self.data.get("updated_at") or self.data.get("started_at")
            if ts:
                stored_date = str(ts)[:10]
        if not stored_date:
            return False
        return stored_date < today

    async def load(self) -> dict[str, Any]:
        """Load checkpoint state from MongoDB db.crawler_checkpoints. Resets automatically on new calendar day."""
        try:
            db = get_db()
            doc = await db.crawler_checkpoints.find_one({"_id": self.doc_id})
            if doc:
                self.data = dict(doc)
        except Exception as e:
            logger.warning("Could not read checkpoint from async MongoDB, trying sync fallback", error=str(e))
            self._load_sync()

        # Automatic daily rollover check
        if self.should_reset_daily():
            prev_date = self.data.get("crawl_date") or str(self.data.get("updated_at", ""))[:10]
            logger.info("Crawl checkpoint belongs to previous date; performing daily reset", previous_date=prev_date, today=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            await self.reset()
        elif not self.data.get("crawl_date"):
            self.data["crawl_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        return self.data

    def _load_sync(self) -> None:
        try:
            from pymongo import MongoClient
            from app.core.config import get_settings
            client = MongoClient(get_settings().mongodb_uri, serverSelectionTimeoutMS=1500)
            doc = client[get_settings().mongodb_db_name]["crawler_checkpoints"].find_one({"_id": self.doc_id})
            if doc:
                self.data = dict(doc)
                if self.should_reset_daily():
                    self._reset_sync()
                elif not self.data.get("crawl_date"):
                    self.data["crawl_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            client.close()
        except Exception:
            pass

    async def save(self) -> None:
        """Persist checkpoint state to MongoDB db.crawler_checkpoints."""
        self.data["updated_at"] = datetime.now(timezone.utc).isoformat()
        if not self.data.get("crawl_date"):
            self.data["crawl_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            db = get_db()
            await db.crawler_checkpoints.replace_one(
                {"_id": self.doc_id},
                self.data,
                upsert=True,
            )
        except Exception as e:
            logger.error("Failed to save checkpoint to async MongoDB, trying sync fallback", error=str(e))
            self._save_sync()

    def _save_sync(self) -> None:
        try:
            from pymongo import MongoClient
            from app.core.config import get_settings
            client = MongoClient(get_settings().mongodb_uri, serverSelectionTimeoutMS=1500)
            if not self.data.get("crawl_date"):
                self.data["crawl_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            client[get_settings().mongodb_db_name]["crawler_checkpoints"].replace_one(
                {"_id": self.doc_id},
                self.data,
                upsert=True,
            )
            client.close()
        except Exception as e:
            logger.error("Failed sync checkpoint save to MongoDB", error=str(e))

    async def reset(self) -> None:
        """Reset checkpoint in MongoDB for the current day."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.data = {
            "_id": self.doc_id,
            "crawl_date": today,
            "source_file": self.data.get("source_file", ""),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "completed_ranks": [],
            "completed_companies": [],
            "stats": {
                "total_crawled": 0,
                "total_jobs_discovered": 0,
                "total_jobs_saved": 0,
                "captchas_encountered": 0,
                "errors_encountered": 0,
            },
            "history": [],
        }
        try:
            db = get_db()
            await db.crawler_checkpoints.replace_one(
                {"_id": self.doc_id},
                self.data,
                upsert=True,
            )
        except Exception:
            self._reset_sync()

    def _reset_sync(self) -> None:
        try:
            from pymongo import MongoClient
            from app.core.config import get_settings
            client = MongoClient(get_settings().mongodb_uri, serverSelectionTimeoutMS=1500)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            self.data = {
                "_id": self.doc_id,
                "crawl_date": today,
                "source_file": self.data.get("source_file", ""),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "completed_ranks": [],
                "completed_companies": [],
                "stats": {
                    "total_crawled": 0,
                    "total_jobs_discovered": 0,
                    "total_jobs_saved": 0,
                    "captchas_encountered": 0,
                    "errors_encountered": 0,
                },
                "history": [],
            }
            client[get_settings().mongodb_db_name]["crawler_checkpoints"].replace_one(
                {"_id": self.doc_id},
                self.data,
                upsert=True,
            )
            client.close()
        except Exception:
            pass

    def is_completed(self, rank: int, company_name: str | None = None) -> bool:
        if rank in self.data.get("completed_ranks", []):
            return True
        if company_name and company_name in self.data.get("completed_companies", []):
            return True
        return False

    async def record_company(
        self,
        rank: int,
        company_name: str,
        url: str,
        status: str,
        jobs_found: int,
        jobs_new: int,
        error_msg: str | None = None,
    ) -> None:
        if rank not in self.data["completed_ranks"]:
            self.data["completed_ranks"].append(rank)

        comps = self.data.setdefault("completed_companies", [])
        if company_name not in comps:
            comps.append(company_name)

        stats = self.data.setdefault("stats", {})
        stats["total_crawled"] = stats.get("total_crawled", 0) + 1
        stats["total_jobs_discovered"] = stats.get("total_jobs_discovered", 0) + jobs_found
        stats["total_jobs_saved"] = stats.get("total_jobs_saved", 0) + jobs_new

        if "CAPTCHA" in status:
            stats["captchas_encountered"] = stats.get("captchas_encountered", 0) + 1
        elif "ERROR" in status:
            stats["errors_encountered"] = stats.get("errors_encountered", 0) + 1

        self.data.setdefault("history", []).append({
            "rank": rank,
            "company_name": company_name,
            "url": url,
            "status": status,
            "jobs_found": jobs_found,
            "jobs_new": jobs_new,
            "error": error_msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await self.save()


# ---------------------------------------------------------------------------
# Company Data Loader
# ---------------------------------------------------------------------------

def resolve_target_file(custom_path: str | None = None) -> str:
    """Find the company list JSON file from specified arg or standard locations."""
    if custom_path and os.path.isfile(custom_path):
        return os.path.abspath(custom_path)

    for p in DEFAULT_JSON_PATHS:
        if os.path.isfile(p):
            return p

    raise FileNotFoundError(
        f"Could not find Delhi NCR tech companies JSON file. Checked: {DEFAULT_JSON_PATHS}"
    )


def load_companies(
    file_path: str,
    grade_filter: list[str] | None = None,
    skip_placeholders: bool = True,
    start_rank: int | None = None,
    end_rank: int | None = None,
    name_filter: list[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Load and filter companies from JSON dataset."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        title = "Delhi NCR Tech Companies"
        raw_list = data
    else:
        title = data.get("title", "Delhi NCR Tech Companies")
        raw_list = data.get("companies", [])

    filtered: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_list, 1):
        if not item.get("is_active", True):
            continue

        rank = item.get("rank") or idx
        name = (item.get("company_name") or item.get("name") or "").strip()
        url = (item.get("final_url") or item.get("career_page") or item.get("url") or "").strip()
        raw_grade = str(item.get("grade", "B")).strip()
        grade = raw_grade.upper()

        # Map common tier names: Tier-1 -> S, Tier-2 -> A
        if grade == "TIER-1":
            grade = "S"
        elif grade == "TIER-2":
            grade = "A"

        is_placeholder = bool(
            "placeholder" in url.lower() or name.startswith("Delhi NCR Tech Company #")
        )
        verified = item.get("verified", not is_placeholder)

        # Skip invalid or empty URLs
        if not url or not url.startswith("http"):
            continue

        # Skip placeholders
        if skip_placeholders and is_placeholder:
            continue

        # Rank range filtering
        if start_rank is not None and rank < start_rank:
            continue
        if end_rank is not None and end_rank < rank:
            continue

        # Grade filter
        if grade_filter and grade not in grade_filter and raw_grade.upper() not in grade_filter:
            continue

        # Name filter
        if name_filter:
            if not any(nf.lower() in name.lower() for nf in name_filter):
                continue

        filtered.append({
            "rank": rank,
            "name": name,
            "url": url,
            "grade": grade,
            "verified": verified,
            "location_hq": item.get("location_hq", ""),
            "industry": item.get("industry", ""),
            "ats_type": item.get("ats_type", ""),
        })

    # Sort deterministically by rank
    filtered.sort(key=lambda x: x["rank"])
    return title, filtered


# ---------------------------------------------------------------------------
# Job Normalization & Persistence
# ---------------------------------------------------------------------------

async def save_and_match_job(raw_job: Any, db: Any, users: list[dict], matcher: JobMatcherAgent) -> tuple[bool, dict | None]:
    """Normalize, persist to db.jobs with source='career-crawled', and compute matches."""
    if not is_relevant_tech_job(raw_job.title):
        logger.debug("Skipping non-relevant non-tech job", company=raw_job.company, title=raw_job.title)
        return False, None

    if not is_delhi_ncr_or_remote_job(raw_job.location, raw_job.title, raw_job.description or ""):
        logger.debug("Skipping non-Delhi-NCR non-Remote job", company=raw_job.company, title=raw_job.title, location=raw_job.location)
        return False, None

    from app.core.retention import is_older_than_retention
    if is_older_than_retention(getattr(raw_job, "posted_at", None)):
        logger.debug("Skipping job older than 2 months", company=raw_job.company, title=raw_job.title)
        return False, None

    content_hash = JobDeduplicator.compute_raw_hash(raw_job)

    # Check deduplication
    exists_query: dict[str, Any] = (
        {"$or": [{"content_hash": content_hash}, {"external_id": raw_job.external_id}]}
        if getattr(raw_job, "external_id", None)
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
        "company_info": {"website": getattr(raw_job, "company_website", None) or norm["source_url"]},
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
        "posted_at": getattr(raw_job, "posted_at", None) or now,
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
                    "updated_at": now,
                }
            },
        )
        is_new = False
    else:
        insert_res = await db.jobs.insert_one(job_doc)
        job_id = insert_res.inserted_id
        is_new = True

    # Calculate match scores for all active candidates
    for u in users:
        try:
            await matcher.match_user_and_job(
                user_id=str(u["_id"]),
                job_id=str(job_id),
                use_ai_reasoning=False,
            )
        except Exception:
            pass

    return is_new, job_doc


# ---------------------------------------------------------------------------
# Main Crawler Loop
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(
        description="Resumable Delhi NCR Tech Career Crawler (reading top_500_delhi_ncr_tech.json)."
    )
    parser.add_argument("--file", "-f", default=None, help="Path to companies JSON dataset (default: top_500_delhi_ncr_tech.json)")
    parser.add_argument("--query", "-q", default=None, help="Role keyword query (defaults to user profile target role)")
    parser.add_argument("--companies", "-c", default=None, help="Comma-separated company names to filter (e.g. 'zomato,blinkit,paytm')")
    parser.add_argument("--grade", "-g", default=None, help="Filter by tier grades (e.g. 'S' or 'S,A')")
    parser.add_argument("--start-rank", type=int, default=None, help="Start from this rank number (e.g. 1)")
    parser.add_argument("--end-rank", type=int, default=None, help="End at this rank number (e.g. 25)")
    parser.add_argument("--max-companies", "-m", type=int, default=None, help="Max number of companies to crawl in this run")
    parser.add_argument("--limit-per-company", type=int, default=5, help="Max jobs to extract per company (default: 5)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode (default: True)")
    parser.add_argument("--visible", action="store_false", dest="headless", help="Show browser GUI during crawl")
    parser.add_argument("--slow-mo", type=int, default=50, help="Playwright slow-mo delay in ms (default: 50)")
    parser.add_argument("--model", default="llama3.2:latest", help="Ollama AI model to drive navigation (default: llama3.2:latest)")
    parser.add_argument("--concurrency", type=int, default=3, help="Number of concurrent browser workers (default: 3)")
    parser.add_argument("--restart", action="store_true", default=False, help="Reset checkpoint and start from rank 1")
    parser.add_argument("--checkpoint-id", default=DEFAULT_CHECKPOINT_ID, help="MongoDB checkpoint document ID (default: delhi_ncr_crawler)")
    parser.add_argument("--status", action="store_true", default=False, help="Print current checkpoint progress and exit")
    parser.add_argument("--include-placeholders", action="store_true", default=False, help="Do not skip unverified placeholder entries")

    args = parser.parse_args()

    # Connect to MongoDB
    await connect_db()
    db = get_db()

    # Initialize Checkpoint from MongoDB
    checkpoint = CrawlCheckpoint(args.checkpoint_id)
    await checkpoint.load()

    if args.restart:
        await checkpoint.reset()
        print(f"🔄 MongoDB Checkpoint reset: {args.checkpoint_id}")

    if args.status:
        stats = checkpoint.data.get("stats", {})
        completed = checkpoint.data.get("completed_ranks", [])
        print("\n" + "=" * 70)
        print("📊 CRAWL CHECKPOINT STATUS (MongoDB: db.crawler_checkpoints)")
        print("=" * 70)
        print(f" Checkpoint ID   : {args.checkpoint_id}")
        print(f" Last Updated    : {checkpoint.data.get('updated_at')}")
        print(f" Completed Ranks : {len(completed)} companies")
        print(f" Discovered Jobs : {stats.get('total_jobs_discovered', 0)}")
        print(f" Saved to DB     : {stats.get('total_jobs_saved', 0)}")
        print(f" CAPTCHAs        : {stats.get('captchas_encountered', 0)}")
        print(f" Errors          : {stats.get('errors_encountered', 0)}")
        print("=" * 70 + "\n")
        return

    # Resolve target dataset
    resolved_file = resolve_target_file(args.file)
    checkpoint.data["source_file"] = resolved_file

    grade_filters = [g.strip().upper() for g in args.grade.split(",")] if args.grade else None
    name_filters = [c.strip() for c in args.companies.split(",")] if args.companies else None

    dataset_title, target_companies = load_companies(
        file_path=resolved_file,
        grade_filter=grade_filters,
        skip_placeholders=not args.include_placeholders,
        start_rank=args.start_rank,
        end_rank=args.end_rank,
        name_filter=name_filters,
    )

    if not target_companies:
        print(f"⚠️ No matching companies found in {resolved_file} with current filters.")
        return

    # Slice max companies if specified
    if args.max_companies:
        target_companies = target_companies[: args.max_companies]

    matcher = JobMatcherAgent()
    users = await db.users.find({"is_active": True}).to_list(100)

    # Resolve primary search query from candidate profile target roles
    user_roles = await get_unique_user_selected_roles(db)
    primary_query = args.query or (user_roles[0] if user_roles else "Software Engineer")

    # Graceful exit handler
    stop_event = asyncio.Event()

    def handle_interrupt():
        print("\n\n⚠️ SIGINT received! Finishing current company and saving checkpoint to MongoDB...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_interrupt)
        except NotImplementedError:
            pass

    print("\n" + "=" * 78)
    print(f"🚀 RESUMABLE DELHI NCR TECH CAREER CRAWLER (MongoDB Checkpoint)")
    print("=" * 78)
    print(f" Dataset File       : {resolved_file}")
    print(f" Dataset Title      : {dataset_title}")
    print(f" Target Companies   : {len(target_companies)} companies selected")
    print(f" Already Completed  : {len(checkpoint.data.get('completed_ranks', []))} companies recorded in checkpoint")
    print(f" Default Target Role: {primary_query}")
    print(f" Headless Browser   : {args.headless} (slow-mo: {args.slow_mo}ms)")
    print(f" Active Users       : {len(users)} candidates to match")
    print(f" Checkpoint Doc ID  : {args.checkpoint_id} (in db.crawler_checkpoints)")
    print("=" * 78 + "\n")

    total_new_this_session = 0
    total_found_this_session = 0
    sem = asyncio.Semaphore(max(1, args.concurrency))
    checkpoint_lock = asyncio.Lock()
    active_companies: set[str] = set()

    pending_targets = [
        (idx, t) for idx, t in enumerate(target_companies, 1)
        if not checkpoint.is_completed(t["rank"])
    ]

    print(f"⚡ Running with concurrency = {args.concurrency} ({len(pending_targets)} pending companies)\n")

    async def crawl_worker(idx: int, target: dict[str, Any]):
        nonlocal total_new_this_session, total_found_this_session
        if stop_event.is_set():
            return

        rank = target["rank"]
        comp_name = target["name"]
        career_url = target["url"]
        grade = target["grade"]

        async with sem:
            if stop_event.is_set():
                return

            active_companies.add(comp_name)
            print(f"[{idx}/{len(target_companies)}] 🏢 [Rank #{rank} | Grade {grade}] CRAWLING: {comp_name} ({len(active_companies)} active parallel)")

            jobs = []
            new_count = 0
            worker_agent = AICareerCrawlerAgent(model=args.model)

            try:
                jobs = await worker_agent.crawl_career_portal(
                    company=comp_name,
                    start_url=career_url,
                    target_query=primary_query,
                    headless=args.headless,
                    slow_mo=args.slow_mo,
                    limit=args.limit_per_company,
                )

                for j in jobs:
                    j.source = "career-crawled"
                    is_new, _ = await save_and_match_job(j, db, users, matcher)
                    if is_new:
                        new_count += 1

                async with checkpoint_lock:
                    total_found_this_session += len(jobs)
                    total_new_this_session += new_count
                    status_str = "SUCCESS" if len(jobs) > 0 else "NO_JOBS_FOUND"
                    await checkpoint.record_company(
                        rank=rank,
                        company_name=comp_name,
                        url=career_url,
                        status=status_str,
                        jobs_found=len(jobs),
                        jobs_new=new_count,
                    )
                print(f"     ✅ Completed {comp_name}: {len(jobs)} jobs extracted ({new_count} new entries saved to DB).")

            except CaptchaDetectedException as ce:
                print(f"     🚨 CAPTCHA DETECTED on {comp_name}: {ce.captcha_type}. Logged for manual review.")
                async with checkpoint_lock:
                    await checkpoint.record_company(
                        rank=rank,
                        company_name=comp_name,
                        url=career_url,
                        status=f"CAPTCHA: {ce.captcha_type[:15]}",
                        jobs_found=0,
                        jobs_new=0,
                        error_msg=str(ce),
                    )
                await log_system_event(
                    level="WARNING",
                    category="crawler",
                    message=f"CAPTCHA encountered on {comp_name}: {ce.captcha_type}",
                    details={"company": comp_name, "url": ce.url, "rank": rank},
                )

            except Exception as e:
                logger.error("Error crawling company portal", company=comp_name, rank=rank, error=str(e))
                async with checkpoint_lock:
                    await checkpoint.record_company(
                        rank=rank,
                        company_name=comp_name,
                        url=career_url,
                        status=f"ERROR: {str(e)[:30]}",
                        jobs_found=0,
                        jobs_new=0,
                        error_msg=str(e),
                    )
                print(f"     ❌ Failed {comp_name}: {e}")
            finally:
                active_companies.discard(comp_name)

    await asyncio.gather(*(crawl_worker(idx, t) for idx, t in pending_targets), return_exceptions=True)

    # Summary
    stats = checkpoint.data.get("stats", {})
    print("\n" + "=" * 78)
    print("📊 CRAWL SESSION COMPLETE")
    print("=" * 78)
    print(f" Companies Crawled This Session : {stats.get('total_crawled', 0)}")
    print(f" Jobs Discovered This Session   : {total_found_this_session} ({total_new_this_session} newly inserted into MongoDB)")
    print(f" Total Jobs in Checkpoint Cache : {stats.get('total_jobs_discovered', 0)} ({stats.get('total_jobs_saved', 0)} new)")
    print(f" Checkpoint Saved               : {checkpoint.filepath}")
    print(f" Resume Command                 : python backend/app/scripts/crawl_delhi_ncr_companies.py")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

