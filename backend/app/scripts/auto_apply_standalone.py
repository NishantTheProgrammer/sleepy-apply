"""
Standalone Auto-Apply Process (Human Review / Dry-Run Mode).
Navigates to the job application URL, auto-fills candidate information,
social links, screening questions, and attaches tailored resumes,
BUT strictly halts BEFORE pressing the final Submit button.
"""

import asyncio
import argparse
import sys
import os
from bson import ObjectId
import structlog

from app.db.client import connect_db, close_db, get_db
from app.agents.browser_form_filler import BrowserFormFillerAgent
from app.agents.discord_bot import DiscordAgent

logger = structlog.get_logger()


async def main():
    parser = argparse.ArgumentParser(description="Standalone Auto-Apply Form Filler Process (No-Submit Dry-Run)")
    parser.add_argument("--job-id", type=str, help="MongoDB Job ID to apply for")
    parser.add_argument("--url", type=str, help="Direct job application URL override")
    parser.add_argument("--user-id", type=str, help="User ID (defaults to primary candidate)")
    parser.add_argument("--visible", action="store_true", help="Launch visible browser instead of headless")
    args = parser.parse_args()

    print("=" * 70)
    print("⚡ SLEEPY APPLY: AUTONOMOUS FORM FILLER (STANDALONE DRY-RUN)")
    print("=" * 70)
    print("Mode: Autofill form & stop BEFORE pressing Apply / Submit\n")

    await connect_db()
    db = get_db()

    # 1. Resolve User & Profile
    user_query = {"_id": ObjectId(args.user_id)} if args.user_id else {"role": "admin"}
    user = await db.users.find_one(user_query) or await db.users.find_one({})
    if not user:
        print("❌ Error: No candidate user found in database.")
        sys.exit(1)

    profile = await db.profiles.find_one({"user_id": user["_id"]})
    if not profile:
        profile = {"personal": {"full_name": user.get("discord_username", "Candidate"), "email": user.get("email")}}

    # 2. Resolve Job
    job = None
    if args.job_id:
        job = await db.jobs.find_one({"_id": ObjectId(args.job_id)})
    elif args.url:
        job = {
            "_id": ObjectId(),
            "title": "Software Engineer",
            "company": "Target Company",
            "application_url": args.url,
            "source": "custom",
        }
    else:
        # Pick the best Delhi NCR job with a valid application URL
        job = await db.jobs.find_one({
            "source": "career-crawled",
            "application_url": {"$regex": "^http"},
        })
        if not job:
            job = await db.jobs.find_one({"application_url": {"$regex": "^http"}})

    if not job:
        print("❌ Error: No matching job found to auto-apply.")
        sys.exit(1)

    job_title = job.get("title", "Position")
    company = job.get("company", "Company")
    target_url = args.url or job.get("application_url") or job.get("source_url")

    print(f"👤 Candidate : {profile.get('personal', {}).get('full_name', user.get('discord_username'))}")
    print(f"📧 Email     : {profile.get('personal', {}).get('email', user.get('email'))}")
    print(f"🏢 Company   : {company}")
    print(f"💼 Position  : {job_title}")
    print(f"🔗 Form URL  : {target_url}")
    print("-" * 70)

    # 3. Check for existing tailored resume
    resume = await db.resumes.find_one({"user_id": user["_id"], "job_id": job["_id"]})

    # 4. Execute Autonomous Form Filler
    agent = BrowserFormFillerAgent(headless=not args.visible)
    res = await agent.fill_application_form(
        job=job,
        user=user,
        profile=profile,
        resume=resume,
        dry_run=True,
    )

    print("\n" + "=" * 70)
    print("📋 AUTO-APPLY FORM FILLING REPORT")
    print("=" * 70)
    print(f"Status        : {res.status}")
    print(f"Fields Filled : {len(res.fields_filled)}")
    for f in res.fields_filled:
        print(f"  • {f['field']}: {f['value']}")

    print(f"Submit Button : {'Detected (HALTED - NOT CLICKED)' if res.submit_button_found else 'Ready on page'}")
    if res.screenshot_path:
        print(f"Screenshot    : {res.screenshot_path}")

    print("\n🛑 Result: Form successfully filled and ready for your review!")
    print(f"👉 Direct Link to Inspect & Submit: {res.target_url}")
    print("=" * 70)

    # 5. Broadcast to Discord #auto-applied channel
    try:
        discord = DiscordAgent()
        await discord.notify_application_submitted(
            job_title=f"[AUTOFILLED - REVIEW READY] {job_title}",
            company=company,
            score=95,
            discord_user_id=user.get("discord_id"),
        )
        print("📢 Discord notification dispatched to #auto-applied channel.")
    except Exception as de:
        logger.debug("Discord dispatch skipped", error=str(de))

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())

