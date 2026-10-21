from fastapi import APIRouter, HTTPException, Request, Query, BackgroundTasks
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

    async def run_pipeline():
        try:
            logger.info("Executing on-demand job pipeline for user", user_id=user_id)
            await job_pipeline.ainvoke({"user_id": user_id})
        except Exception as e:
            logger.error("On-demand job pipeline failed", user_id=user_id, error=str(e))

    background_tasks.add_task(run_pipeline)
    return {"ok": True, "message": "Job discovery and matching started in background"}


@router.get("")
async def list_jobs(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    min_score: int = Query(0, ge=0, le=100),
    status: str | None = None,
):
    """Return jobs matched to the user, sorted by compatibility score."""
    user_id = get_current_user_id(request)
    db = get_db()
    skip = (page - 1) * limit

    match_filter: dict = {"user_id": ObjectId(user_id)}
    if min_score > 0:
        match_filter["compatibility_score"] = {"$gte": min_score}

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
