#!/usr/bin/env python3
"""
CLI script to run the HR Contact Discovery Agent across job postings in MongoDB.

Usage:
  # Scan next 50 jobs needing HR contact info:
  PYTHONPATH=backend python -m app.scripts.run_hr_finder --limit 50

  # Scan a specific job by ID:
  PYTHONPATH=backend python -m app.scripts.run_hr_finder --job-id 6af58458e38c8c320cb61a36

  # Force re-scan across all active jobs:
  PYTHONPATH=backend python -m app.scripts.run_hr_finder --all --force
"""
import argparse
import asyncio
import os
import sys

# Ensure backend root is in sys.path
backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.db.client import connect_db, get_db
from app.agents.hr_contact_finder import hr_contact_finder
from bson import ObjectId


async def main():
    parser = argparse.ArgumentParser(description="Run HR Contact Finder Agent")
    parser.add_argument("--job-id", type=str, help="Enrich a specific job by MongoDB ObjectId")
    parser.add_argument("--limit", type=int, default=50, help="Number of jobs to process (default: 50)")
    parser.add_argument("--all", action="store_true", help="Process all active jobs")
    parser.add_argument("--force", action="store_true", help="Force re-scan even if contact already exists")
    parser.add_argument("--live", action="store_true", help="Attempt live web page fetch if missing in text")
    args = parser.parse_args()

    print("🔌 Connecting to MongoDB...")
    await connect_db()
    db = get_db()

    if args.job_id:
        print(f"🎯 Running HR Contact Discovery for Job ID: {args.job_id}")
        try:
            job = await db.jobs.find_one({"_id": ObjectId(args.job_id)})
            if not job:
                print(f"❌ Job not found: {args.job_id}")
                return

            print(f"   Company: {job.get('company')}")
            print(f"   Title:   {job.get('title')}")
            res = await hr_contact_finder.find_and_enrich_job(job["_id"], fetch_live=args.live)
            print("\n✨ Discovered HR Contact Details:")
            print(f"   👤 Name:        {res.get('name') or 'N/A'}")
            print(f"   💼 Title:       {res.get('designation') or 'N/A'}")
            print(f"   ✉️  Email:       {res.get('email') or 'N/A'}")
            print(f"   📞 Phone:       {res.get('phone') or 'N/A'}")
            print(f"   🔗 LinkedIn:    {res.get('linkedin') or 'N/A'}")
            print(f"   🛡️ Confidence:  {res.get('confidence')}")
            print(f"   📍 Source:      {res.get('source')}")
        except Exception as e:
            print(f"❌ Error: {e}")
        return

    # Batch processing
    limit = 999999 if args.all else args.limit
    print(f"🚀 Batch running HR Contact Discovery Agent (limit={limit}, force={args.force})...")
    query = {"is_active": True}
    if not args.force:
        query["$or"] = [
            {"hr_contact": None},
            {"hr_contact": {}},
            {"hr_contact.email": None},
            {"hr_contact.source": "company_domain_synthesis"},
        ]

    cursor = db.jobs.find(query).limit(limit)
    total = await db.jobs.count_documents(query)
    print(f"📊 Jobs matching criteria: {total} (processing up to {limit})\n")

    processed = 0
    direct_found = 0

    async for job in cursor:
        job_id = job["_id"]
        company = job.get("company", "Company")
        title = job.get("title", "Role")
        try:
            res = await hr_contact_finder.find_and_enrich_job(job_id, fetch_live=args.live)
            processed += 1
            conf = res.get("confidence")
            email = res.get("email")
            phone = res.get("phone")

            if conf in ["high", "medium"]:
                direct_found += 1
                status = f"✅ [DIRECT] {company} | {res.get('name') or 'Recruiter'} | {email or ''} | {phone or ''}"
            else:
                status = f"ℹ️  [INFERRED] {company} | {email or 'No email'}"

            print(f"[{processed}/{min(total, limit)}] {status}")
        except Exception as e:
            print(f"⚠️  Error enriching {company} ({job_id}): {e}")

    print("\n" + "=" * 60)
    print(f"🎉 Completed! Processed: {processed} jobs | Direct contacts found: {direct_found}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

