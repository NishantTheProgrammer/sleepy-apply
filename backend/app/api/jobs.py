from fastapi import APIRouter, HTTPException, Request, Query, BackgroundTasks
from pydantic import BaseModel
from bson import ObjectId
from app.db.client import get_db
from app.security.jwt import get_current_user_id
import structlog

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = structlog.get_logger()


@router.post("/fetch-now")
async def trigger_fetch_now(request: Request, background_tasks: BackgroundTasks):
    """Trigger job discovery and matching pipeline for current user."""
    user_id = get_current_user_id(request)
    from app.graphs.job_pipeline_graph import job_pipeline
    from app.agents.job_matcher import JobMatcherAgent
    from app.models.settings import UserSettings

    # Fast-match all existing jobs in the repository for immediate UI response
    try:
        db = get_db()
        matcher = JobMatcherAgent()
        settings_doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
        user_settings = UserSettings(**settings_doc) if settings_doc else None
        cursor = db.jobs.find({"is_active": True}).sort("discovered_at", -1).limit(250)
        async for j in cursor:
            await matcher.match_user_and_job(user_id, str(j["_id"]), user_settings=user_settings, use_ai_reasoning=False)
    except Exception as e:
        logger.warning("Fast job matching failed", error=str(e), user_id=user_id)

    async def run_pipeline():
        try:
            logger.info("Executing on-demand job pipeline for user", user_id=user_id)
            await job_pipeline.ainvoke({"user_id": user_id})
        except Exception as e:
            logger.error("On-demand job pipeline failed", user_id=user_id, error=str(e))

    background_tasks.add_task(run_pipeline)
    return {"ok": True, "message": "Jobs matched and discovery running in background"}


class CrawlDelhiNCRRequest(BaseModel):
    companies: list[str] | None = None
    concurrency: int = 3
    restart: bool = False


@router.post("/crawl-delhi-ncr")
async def trigger_crawl_delhi_ncr(
    request: Request,
    background_tasks: BackgroundTasks,
    body: CrawlDelhiNCRRequest | None = None,
):
    """Trigger resumable Delhi NCR career crawler for current candidate."""
    user_id = get_current_user_id(request)
    from app.agents.crawler_manager import crawler_manager
    status = crawler_manager.get_status()
    if status.get("is_running"):
        return {"ok": False, "message": "Delhi NCR crawler is already active and running."}

    req = body or CrawlDelhiNCRRequest()
    if req.restart:
        from app.scripts.crawl_delhi_ncr_companies import CrawlCheckpoint
        await CrawlCheckpoint().reset()

    async def _runner():
        await crawler_manager.run_batch(
            companies=req.companies,
            headless=True,
            limit_per_company=5,
            concurrency=req.concurrency,
        )

    background_tasks.add_task(_runner)
    return {
        "ok": True,
        "message": f"AI Browser Crawler started across top Delhi NCR tech companies ({req.concurrency}x parallel). Postings will appear under 'Career Crawled'.",
        "status": crawler_manager.get_status(),
    }


@router.get("/crawler-status")
async def get_user_crawler_status(request: Request):
    """Retrieve live status of the Delhi NCR crawler for candidate UI."""
    get_current_user_id(request)
    from app.agents.crawler_manager import crawler_manager
    from app.scripts.crawl_delhi_ncr_companies import CrawlCheckpoint
    status = crawler_manager.get_status()
    checkpoint = CrawlCheckpoint()
    await checkpoint.load()
    status["checkpoint"] = {
        "crawl_date": checkpoint.data.get("crawl_date"),
        "completed_count": len(checkpoint.data.get("completed_ranks", [])),
        "total_jobs_discovered": checkpoint.data.get("stats", {}).get("total_jobs_discovered", 0),
        "total_jobs_saved": checkpoint.data.get("stats", {}).get("total_jobs_saved", 0),
    }
    return status


@router.get("")
async def list_jobs(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    min_score: int = Query(0, ge=0, le=100),
    source: str | None = None,
    status: str | None = None,
):
    """Return jobs matched to the user, sorted by compatibility score and optionally filtered by source."""
    user_id = get_current_user_id(request)
    db = get_db()
    skip = (page - 1) * limit

    match_filter: dict = {"user_id": ObjectId(user_id)}
    if min_score > 0:
        match_filter["compatibility_score"] = {"$gte": min_score}
    if source and source != "all":
        source_job_ids = await db.jobs.distinct("_id", {"source": source})
        match_filter["job_id"] = {"$in": source_job_ids}

    # Join matches with jobs and applications
    pipeline = [
        {"$match": match_filter},
        {"$sort": {"compatibility_score": -1}},
        {"$skip": skip},
        {"$limit": limit},
        {
            "$lookup": {
                "from": "jobs",
                "localField": "job_id",
                "foreignField": "_id",
                "as": "job",
            }
        },
        {"$unwind": "$job"},
        {
            "$lookup": {
                "from": "applications",
                "let": {"jid": "$job_id", "uid": "$user_id"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$job_id", "$$jid"]},
                                    {"$eq": ["$user_id", "$$uid"]},
                                ]
                            }
                        }
                    }
                ],
                "as": "application",
            }
        },
        {"$unwind": {"path": "$application", "preserveNullAndEmptyArrays": True}},
    ]

    cursor = db.job_matches.aggregate(pipeline)
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["user_id"] = str(doc["user_id"])
        doc["job_id"] = str(doc["job_id"])
        doc["job"]["_id"] = str(doc["job"]["_id"])
        if doc.get("application"):
            doc["application"]["_id"] = str(doc["application"]["_id"])
        if hasattr(doc.get("resume_generated_at"), "isoformat"):
            doc["resume_generated_at"] = doc["resume_generated_at"].isoformat()
        results.append(doc)

    total = await db.job_matches.count_documents(match_filter)
    return {"items": results, "total": total, "page": page, "limit": limit}


@router.get("/{job_id}")
async def get_job(request: Request, job_id: str):
    """Return a single job with match info and application status."""
    user_id = get_current_user_id(request)
    db = get_db()

    job = await db.jobs.find_one({"_id": ObjectId(job_id)})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job["_id"] = str(job["_id"])

    match = await db.job_matches.find_one(
        {"job_id": ObjectId(job_id), "user_id": ObjectId(user_id)}
    )
    if match:
        match["_id"] = str(match["_id"])
        match["user_id"] = str(match["user_id"])
        match["job_id"] = str(match["job_id"])
        if hasattr(match.get("resume_generated_at"), "isoformat"):
            match["resume_generated_at"] = match["resume_generated_at"].isoformat()

    application = await db.applications.find_one(
        {"job_id": ObjectId(job_id), "user_id": ObjectId(user_id)}
    )
    if application:
        application["_id"] = str(application["_id"])
        application["user_id"] = str(application["user_id"])
        application["job_id"] = str(application["job_id"])

    return {"job": job, "match": match, "application": application}


@router.post("/{job_id}/apply")
async def trigger_apply(request: Request, job_id: str):
    """Manually trigger the application pipeline for a specific job."""
    user_id = get_current_user_id(request)
    db = get_db()

    # Check job exists and user has a match
    job = await db.jobs.find_one({"_id": ObjectId(job_id)})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Prevent duplicate applications
    existing = await db.applications.find_one(
        {
            "job_id": ObjectId(job_id),
            "user_id": ObjectId(user_id),
            "status": {"$in": ["APPLIED", "APPLYING", "VERIFIED_SUCCESS"]},
        }
    )
    if existing:
        raise HTTPException(status_code=409, detail="Application already in progress or submitted")

    import asyncio
    from app.graphs.application_graph import application_pipeline
    asyncio.create_task(application_pipeline.ainvoke({"user_id": user_id, "job_id": job_id}))
    return {"ok": True, "message": "Application pipeline triggered", "job_id": job_id}


@router.post("/{job_id}/generate-resume")
async def generate_tailored_resume(request: Request, job_id: str, template: str | None = None):
    """Generate tailored resume JSON against user profile and JD, and store against job-user match."""
    user_id = get_current_user_id(request)
    tpl = template
    if not tpl:
        try:
            body = await request.json()
            tpl = body.get("template")
        except Exception:
            pass

    from app.agents.resume_builder import ResumeBuilderAgent

    agent = ResumeBuilderAgent()
    result = await agent.build_tailored_resume(user_id=user_id, job_id=job_id, template=tpl)
    if not result:
        raise HTTPException(status_code=400, detail="Could not generate tailored resume. Check if profile and job exist.")

    # Broadcast notification to Discord #tailored channel
    try:
        from app.agents.discord_bot import DiscordAgent
        import asyncio
        db = get_db()
        user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
        discord_id = (user_doc or {}).get("discord_id")
        content = result.get("content", {})
        headline = content.get("target_headline") or content.get("job_title", "")
        matched_skills = content.get("matching_skills", [])
        score = content.get("compatibility_score", 0)
        discord_agent = DiscordAgent()
        asyncio.create_task(
            discord_agent.notify_tailored_resume_ready(
                job_title=content.get("job_title", "Role"),
                company=content.get("company", "Company"),
                headline=headline,
                matched_skills_count=len(matched_skills),
                score=score,
                discord_user_id=discord_id,
            )
        )
    except Exception as e:
        logger.warning("Discord tailored notification dispatch failed", error=str(e))

    return {
        "ok": True,
        "job_id": job_id,
        "tailored_resume": result.get("content"),
        "generated_at": result.get("generated_at"),
        "docx_path": result.get("docx_path"),
    }


@router.get("/{job_id}/resume")
async def get_tailored_resume(request: Request, job_id: str):
    """Get the stored tailored resume JSON for this job and user."""
    user_id = get_current_user_id(request)
    db = get_db()

    match = await db.job_matches.find_one(
        {"job_id": ObjectId(job_id), "user_id": ObjectId(user_id)}
    )
    if match and match.get("tailored_resume"):
        gen_at = match.get("resume_generated_at")
        if hasattr(gen_at, "isoformat"):
            gen_at = gen_at.isoformat()
        return {
            "ok": True,
            "job_id": job_id,
            "tailored_resume": match.get("tailored_resume"),
            "generated_at": gen_at,
        }

    # Fallback check in db.resumes
    resume = await db.resumes.find_one(
        {"job_id": ObjectId(job_id), "user_id": ObjectId(user_id)}
    )
    if resume and resume.get("content"):
        gen_at = resume.get("generated_at")
        if hasattr(gen_at, "isoformat"):
            gen_at = gen_at.isoformat()
        return {
            "ok": True,
            "job_id": job_id,
            "tailored_resume": resume.get("content"),
            "generated_at": gen_at,
        }

    return {"ok": False, "tailored_resume": None}


@router.delete("/{job_id}/resume")
async def delete_tailored_resume(request: Request, job_id: str):
    """Delete a tailored resume for this job and user, cleaning up MongoDB records and files."""
    user_id = get_current_user_id(request)
    db = get_db()
    import os

    # 1. Clear tailored resume from db.job_matches
    await db.job_matches.update_one(
        {"job_id": ObjectId(job_id), "user_id": ObjectId(user_id)},
        {
            "$unset": {
                "tailored_resume": "",
                "resume_generated_at": "",
                "resume_docx_path": "",
            }
        },
    )

    # 2. Find and delete from db.resumes
    resume = await db.resumes.find_one(
        {"job_id": ObjectId(job_id), "user_id": ObjectId(user_id)}
    )
    if resume:
        # Clean up files on disk if present
        for fpath_key in ("docx_path", "pdf_path"):
            fpath = resume.get(fpath_key)
            if fpath and os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception as e:
                    logger.warning("Could not delete resume file on disk", path=fpath, error=str(e))
        await db.resumes.delete_one({"_id": resume["_id"]})

    logger.info("Tailored resume deleted", user_id=user_id, job_id=job_id)
    return {"ok": True, "message": "Tailored resume deleted successfully", "job_id": job_id}


@router.get("/{job_id}/resume/download")
async def download_tailored_resume_docx(request: Request, job_id: str, template: str | None = None):
    """Download the tailored .docx resume for this job and user."""
    user_id = get_current_user_id(request)
    db = get_db()
    from fastapi.responses import StreamingResponse

    # Check match or resume document
    match = await db.job_matches.find_one(
        {"job_id": ObjectId(job_id), "user_id": ObjectId(user_id)}
    )
    tailored = match.get("tailored_resume") if match else None

    if not tailored:
        resume = await db.resumes.find_one(
            {"job_id": ObjectId(job_id), "user_id": ObjectId(user_id)}
        )
        if resume:
            tailored = resume.get("content")

    # If still not generated, generate on the fly
    if not tailored:
        from app.agents.resume_builder import ResumeBuilderAgent
        agent = ResumeBuilderAgent()
        res = await agent.build_tailored_resume(user_id=user_id, job_id=job_id, template=template)
        if res:
            tailored = res.get("content")

    if not tailored:
        raise HTTPException(status_code=404, detail="Tailored resume not found")

    from app.templates.manager import render_docx_for_profile
    profile = await db.profiles.find_one({"user_id": ObjectId(user_id)}) or {}
    template_id = template or tailored.get("template") or profile.get("selected_template") or "default"

    tailored_context = {
        **profile,
        "summary": tailored.get("tailored_summary") or tailored.get("summary") or profile.get("summary", ""),
        "skills": tailored.get("skills") or profile.get("skills", {}),
        "experience": tailored.get("experience") or profile.get("experience", []),
        "projects": tailored.get("projects") if tailored.get("projects") is not None else profile.get("projects", []),
        "matching_skills": tailored.get("matching_skills", []),
    }

    try:
        stream = render_docx_for_profile(template_id, tailored_context)
    except Exception as e:
        logger.error("Failed to render docx", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to render document")

    company = tailored.get("company", "Job").replace(" ", "_")
    title = tailored.get("job_title", "Role").replace(" ", "_")
    filename = f"Resume_{company}_{title}.docx"

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
