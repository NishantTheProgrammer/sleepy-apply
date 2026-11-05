#!/usr/bin/env python3
import sys
import os
import argparse
import asyncio
import urllib.parse

# Ensure backend root is in sys.path
backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.sources.playwright_crawler import PlaywrightJobCrawler
from app.sources.ai_crawler import AICareerCrawlerAgent


async def main():
    parser = argparse.ArgumentParser(description="Test Career Crawler (Standard or Autonomous AI Agent).")
    parser.add_argument("--url", required=True, help="Career Page URL (e.g. 'https://www.exlservice.com/careers')")
    parser.add_argument("--company", default=None, help="Company name (optional; defaults to domain)")
    parser.add_argument("--query", "-q", default=None, help="Role or job keyword to search for (activates AI Agent)")
    parser.add_argument("--ai", action="store_true", default=False, help="Explicitly enable AI Browser Agent")
    parser.add_argument("--headless", action="store_true", default=False, help="Run in headless mode (default: False / visible browser)")
    parser.add_argument("--delhi-ncr-only", action="store_true", default=False, help="Filter strictly for Delhi NCR jobs")
    parser.add_argument("--limit", type=int, default=10, help="Max jobs to extract (default: 10)")
    parser.add_argument("--slow-mo", type=int, default=100, help="Delay per action in ms (default: 100ms)")
    parser.add_argument("--model", default="llama3.2:latest", help="Ollama AI model to drive the agent (default: llama3.2:latest)")

    args = parser.parse_args()

    # Determine company name
    comp_name = args.company
    if not comp_name:
        domain = urllib.parse.urlparse(args.url).netloc.replace("www.", "")
        comp_name = domain.split(".")[0].title()

    # If --query is provided or --ai is set, use the AI Agent
    if args.query or args.ai:
        target_role = args.query or "Software Engineer"
        agent = AICareerCrawlerAgent(model=args.model)
        jobs = await agent.crawl_career_portal(
            company=comp_name,
            start_url=args.url,
            target_query=target_role,
            headless=args.headless,
            slow_mo=args.slow_mo,
            delhi_ncr_only=args.delhi_ncr_only,
            limit=args.limit,
        )
    else:
        # Standard crawler
        crawler = PlaywrightJobCrawler(headless=args.headless)
        jobs = await crawler.fetch_jobs({
            "companies": [{"name": comp_name, "career_page": args.url}],
            "delhi_ncr_only": args.delhi_ncr_only,
            "limit_per_company": args.limit,
            "headless": args.headless,
            "slow_mo": args.slow_mo,
        })

    print("\n" + "=" * 70)
    print(f"🎯 RESULTS: Found {len(jobs)} jobs for {comp_name}")
    print("=" * 70)

    if not jobs:
        print("⚠️ No jobs extracted from this session.")
        return

    for idx, j in enumerate(jobs, 1):
        remote_tag = " [REMOTE]" if j.is_remote else ""
        print(f"[{idx:02d}] {j.title}")
        print(f"     📍 Location: {j.location}{remote_tag}")
        print(f"     🔗 URL: {j.application_url}")
        print("-" * 70)

    print(f"\n✅ Total successfully extracted: {len(jobs)} postings.\n")


if __name__ == "__main__":
    asyncio.run(main())
