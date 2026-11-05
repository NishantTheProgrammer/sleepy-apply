#!/usr/bin/env python3
"""
Batch Career Crawler for 10 Target Companies.
Crawls career portals using the AI Browser Agent, marks postings as 'career-crawled',
persists them into MongoDB (db.jobs), and computes user match scores.
"""
import sys
import os
import argparse
import asyncio
from datetime import datetime, timezone
import structlog

# Ensure backend root is in sys.path
backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.db.client import connect_db, get_db
from app.sources.ai_crawler import AICareerCrawlerAgent, CaptchaDetectedException
from app.core.system_logger import log_system_event
from app.pipeline.normalizer import DelhiNCRJobNormalizer
from app.pipeline.deduplicator import JobDeduplicator
from app.agents.job_matcher import JobMatcherAgent
from app.pipeline.role_search import get_unique_user_selected_roles

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


async def save_and_match_job(raw_job, db, users, matcher):
    """Normalize, persist to db.jobs with source='career-crawled', and compute matches."""
    content_hash = JobDeduplicator.compute_raw_hash(raw_job)

    # Check deduplication
    exists_query = {"$or": [{"content_hash": content_hash}, {"external_id": raw_job.external_id}]} if raw_job.external_id else {"content_hash": content_hash}
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
        "posted_at": raw_job.posted_at or now,
        "is_active": True,
        "enriched": False,
        "content_hash": content_hash,
        "discovered_at": now,
    }

    if existing:
        job_id = existing["_id"]
        # Update existing record with refreshed source and timestamp
        await db.jobs.update_one(
            {"_id": job_id},
            {"$set": {"source": "career-crawled", "is_active": True, "location": norm["location"]}}
        )
        is_new = False
    else:
        insert_res = await db.jobs.insert_one(job_doc)
        job_id = insert_res.inserted_id
        is_new = True

    # Calculate match scores for all active users
    for u in users:
        try:
            await matcher.match_user_and_job(
                user_id=str(u["_id"]),
                job_id=str(job_id),
                use_ai_reasoning=False
            )
        except Exception:
            pass

    return is_new, job_doc


async def main():
    parser = argparse.ArgumentParser(description="Batch AI Career Crawler for 10 Target Companies.")
    parser.add_argument("--query", "-q", default=None, help="Target role query (defaults to user-selected profile roles)")
    parser.add_argument("--companies", "-c", default=None, help="Comma-separated company names to filter (e.g. 'mongodb,exl,stripe')")
    parser.add_argument("--headless", action="store_true", default=False, help="Run headless (default: False / visible browser)")
    parser.add_argument("--limit-per-company", type=int, default=5, help="Max jobs to extract per company (default: 5)")
    parser.add_argument("--slow-mo", type=int, default=100, help="Playwright slow-mo delay in ms (default: 100)")
    parser.add_argument("--model", default="llama3.2:latest", help="Ollama model for AI Agent (default: llama3.2:latest)")

    args = parser.parse_args()

    await connect_db()
    db = get_db()
    matcher = JobMatcherAgent()
    users = await db.users.find({"is_active": True}).to_list(100)

    # Determine search queries
    user_roles = await get_unique_user_selected_roles(db)
    primary_query = args.query or (user_roles[0] if user_roles else None)

    # Filter target companies if requested
    selected_targets = TARGET_COMPANIES
    if args.companies:
        filter_names = [f.strip().lower() for f in args.companies.split(",") if f.strip()]
        selected_targets = [
            t for t in TARGET_COMPANIES
            if any(fn in t["name"].lower() for fn in filter_names)
        ]

    print("\n" + "=" * 75)
    print("🚀 BATCH AI CAREER CRAWLER FOR 10 TARGET COMPANIES")
    print("=" * 75)
    print(f" Companies to Crawl : {len(selected_targets)}")
    print(f" Default Target Role: {primary_query or 'Role-specific default'}")
    print(f" Category Tag       : 'career-crawled' (visible in Web UI)")
    print(f" Visible Browser GUI: {not args.headless} (slow-mo: {args.slow_mo}ms)")
    print(f" Active Users Matched: {len(users)}")
    print("=" * 75 + "\n")

    agent = AICareerCrawlerAgent(model=args.model)
    total_discovered = 0
    total_saved = 0
    summary_report = []

    for idx, target in enumerate(selected_targets, 1):
        comp_name = target["name"]
        career_url = target["url"]
        query_role = primary_query or target.get("default_query", "Software Engineer")

        print(f"\n[{idx}/{len(selected_targets)}] 🏢 CRAWLING: {comp_name}")
        print(f"     URL  : {career_url}")
        print(f"     Query: '{query_role}'")

        try:
            jobs = await agent.crawl_career_portal(
                company=comp_name,
                start_url=career_url,
                target_query=query_role,
                headless=args.headless,
                slow_mo=args.slow_mo,
                limit=args.limit_per_company,
            )

            new_count = 0
            for j in jobs:
                j.source = "career-crawled"
                is_new, _ = await save_and_match_job(j, db, users, matcher)
                if is_new:
                    new_count += 1

            total_discovered += len(jobs)
            total_saved += new_count

            summary_report.append({
                "company": comp_name,
                "found": len(jobs),
                "new": new_count,
                "status": "SUCCESS" if len(jobs) > 0 else "NO_JOBS_FOUND",
            })

            print(f"     ✅ Completed {comp_name}: {len(jobs)} found ({new_count} newly added to DB).")

        except CaptchaDetectedException as ce:
            print(f"     🚨 CAPTCHA DETECTED on {comp_name}: {ce.captcha_type}. Crawl aborted as requested.")
            summary_report.append({
                "company": comp_name,
                "found": 0,
                "new": 0,
                "status": f"CAPTCHA: {ce.captcha_type[:15]}",
            })
            await log_system_event(
                level="ERROR",
                category="crawler",
                message=f"Aborted crawl on {comp_name}: {ce.captcha_type} encountered.",
                details={"company": comp_name, "url": ce.url, "captcha_type": ce.captcha_type, "aborted": True}
            )

        except Exception as e:
            logger.error("Failed to crawl company", company=comp_name, error=str(e))
            summary_report.append({
                "company": comp_name,
                "found": 0,
                "new": 0,
                "status": f"ERROR: {str(e)[:35]}",
            })
            print(f"     ❌ Failed {comp_name}: {e}")

    print("\n" + "=" * 75)
    print("📊 BATCH CRAWL COMPLETE - SUMMARY REPORT")
    print("=" * 75)
    print(f"{'Company':<20} | {'Status':<16} | {'Found':<8} | {'New in DB'}")
    print("-" * 75)
    for r in summary_report:
        print(f"{r['company']:<20} | {r['status']:<16} | {r['found']:<8} | {r['new']}")
    print("-" * 75)
    print(f"TOTAL: {total_discovered} jobs discovered across {len(selected_targets)} companies ({total_saved} new entries).")
    print("All postings are tagged with category 'career-crawled' and are available under the '🤖 Career Crawled' tab in your Web UI.")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

