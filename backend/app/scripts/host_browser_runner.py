"""
Host-side Browser Runner Daemon.
Runs natively on macOS (outside Docker) to pop open a real, visible Chromium GUI window (headless: False).
Fills out job application forms step-by-step with deliberate speed (slow_mo=250ms),
outlines the Submit button with a review banner, and keeps the browser window open
so the user can inspect the flow and manually submit.
"""

import asyncio
import os
import sys
from typing import Any
from bson import ObjectId
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import structlog

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db.client import connect_db, get_db
from app.agents.browser_form_filler import BrowserFormFillerAgent

logger = structlog.get_logger()
app = FastAPI(title="Sleepy Apply — Host Browser Runner (Visible Headless: False)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FillVisibleRequest(BaseModel):
    job_id: str | None = None
    user_id: str | None = None
    url: str | None = None


async def _run_visible_filler(job_id: str | None, user_id: str | None, url: str | None):
    try:
        await connect_db()
        db = get_db()

        # Resolve User
        user = None
        if user_id:
            try:
                user = await db.users.find_one({"_id": ObjectId(user_id)})
            except Exception:
                pass
        if not user:
            user = await db.users.find_one({"role": "admin"}) or await db.users.find_one({})

        profile = await db.profiles.find_one({"user_id": user["_id"]}) if user else {}
        if not profile:
            profile = {
                "personal": {
                    "full_name": user.get("discord_username", "Applicant") if user else "Applicant",
                    "email": user.get("email", "applicant@example.com") if user else "applicant@example.com",
                }
            }

        # Resolve Job
        job = None
        if job_id:
            try:
                job = await db.jobs.find_one({"_id": ObjectId(job_id)})
            except Exception:
                pass

        if not job and url:
            job = {
                "_id": ObjectId(),
                "title": "Software Engineer",
                "company": "Target Company",
                "application_url": url,
            }

        if not job:
            job = await db.jobs.find_one({"source": "career-crawled", "application_url": {"$regex": "^http"}})

        if not job:
            logger.error("No valid job found for visible autofill")
            return

        resume = await db.resumes.find_one({"user_id": user["_id"], "job_id": job["_id"]}) if (user and job) else None

        logger.info(
            "🖥️ Launching VISIBLE Chromium window on macOS (headless=False, slow_mo=250ms)...",
            company=job.get("company"),
            title=job.get("title"),
            url=url or job.get("application_url"),
        )

        # Launch VISIBLE browser with deliberate slow_mo so user sees every action live
        agent = BrowserFormFillerAgent(headless=False, slow_mo=250)
        await agent.fill_application_form(
            job=job,
            user=user or {},
            profile=profile or {},
            resume=resume,
            dry_run=True,
            keep_open=True,  # Keeps window open for user review and manual submission
        )
    except Exception as e:
        logger.error("Visible form filler encountered error", error=str(e))


@app.get("/health")
async def health():
    cdp_url = os.environ.get("CHROME_CDP_URL", "http://127.0.0.1:9222")
    cdp_active = BrowserFormFillerAgent._is_cdp_available(cdp_url)
    return {
        "status": "ok",
        "service": "host_browser_runner",
        "environment": "native_macos",
        "mode": "headless_false",
        "cdp_active": cdp_active,
        "profile_mode": "live_chrome_cdp" if cdp_active else "persistent_sleepy_apply_profile",
    }


@app.post("/fill-visible")
async def fill_visible(req: FillVisibleRequest, background_tasks: BackgroundTasks):
    """Triggers the visible browser autofill on macOS host."""
    background_tasks.add_task(_run_visible_filler, req.job_id, req.user_id, req.url)
    return {
        "ok": True,
        "message": "🖥️ Visible browser window launched on your desktop! Watch the form being autofilled in real-time.",
        "job_id": req.job_id,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")

