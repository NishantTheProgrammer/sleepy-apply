from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime, timezone
from bson import ObjectId
from app.db.client import get_db
from app.security.jwt import get_current_user_id
from app.core.config import get_settings
import structlog

router = APIRouter(prefix="/admin", tags=["admin"])
logger = structlog.get_logger()


class UpdateUserRoleRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None


async def require_admin(request: Request) -> str:
    """Dependency: ensure the current user has the admin role. Auto-elevates designated admins."""
    user_id = get_current_user_id(request)
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    settings = get_settings()
    user_email = (user.get("email") or "").lower()
    discord_id = str(user.get("discord_id") or "")

    # Auto-elevate owner/admin if matching configured criteria or single user dev
    if (
        user_email in [e.lower() for e in settings.admin_emails]
        or discord_id in settings.admin_discord_ids
        or (not settings.is_production and await db.users.count_documents({}) <= 1)
    ):
        if user.get("role") != "admin":
            await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"role": "admin"}})
            user["role"] = "admin"
        return user_id

    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id


@router.get("/stats")
async def get_stats(admin_id: str = Depends(require_admin)):
    """Aggregate stats across the platform."""
    db = get_db()
    users = await db.users.count_documents({"is_active": True})
    jobs = await db.jobs.count_documents({"is_active": True})
    applications = await db.applications.count_documents({})
    matches = await db.job_matches.count_documents({})

    # Application status breakdown
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    status_breakdown = {}
    async for doc in db.applications.aggregate(pipeline):
        status_breakdown[doc["_id"]] = doc["count"]

    workflows = await db.workflow_runs.count_documents({"status": "running"})

    return {
        "users": users,
        "active_jobs": jobs,
        "total_applications": applications,
        "total_matches": matches,
        "application_status_breakdown": status_breakdown,
        "active_workflows": workflows,
    }


@router.get("/users")
async def list_users(admin_id: str = Depends(require_admin)):
    db = get_db()
    users = []
    async for u in db.users.find({}, {"__v": 0}):
        u["_id"] = str(u["_id"])
        if u.get("created_at") and hasattr(u["created_at"], "isoformat"):
            u["created_at"] = u["created_at"].isoformat()
        if u.get("last_login") and hasattr(u["last_login"], "isoformat"):
            u["last_login"] = u["last_login"].isoformat()
        if u.get("updated_at") and hasattr(u["updated_at"], "isoformat"):
            u["updated_at"] = u["updated_at"].isoformat()
        users.append(u)
    return {"users": users}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRoleRequest,
    admin_id: str = Depends(require_admin),
):
    db = get_db()
    update: dict = {"updated_at": datetime.now(timezone.utc)}
    if body.role is not None:
        if body.role not in ["user", "admin"]:
            raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'")
        update["role"] = body.role
    if body.is_active is not None:
        update["is_active"] = body.is_active

    await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": update})
    u = await db.users.find_one({"_id": ObjectId(user_id)})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u["_id"] = str(u["_id"])
    return {"ok": True, "user": u}


@router.post("/trigger-discovery")
async def trigger_platform_discovery(
    background_tasks: BackgroundTasks,
    admin_id: str = Depends(require_admin),
):
    """Trigger job ingestion and matching across all active users."""
    from app.graphs.job_pipeline_graph import job_pipeline

    async def run():
        try:
            logger.info("Admin triggered platform job discovery pipeline")
            await job_pipeline.ainvoke({})
        except Exception as e:
            logger.error("Platform job discovery failed", error=str(e))

    background_tasks.add_task(run)
    return {"ok": True, "message": "Platform job discovery triggered in background"}


@router.get("/activity")
async def get_recent_activity(admin_id: str = Depends(require_admin)):
    """Return recent jobs and matches for real-time monitoring."""
    db = get_db()
    recent_jobs = []
    async for j in db.jobs.find({}).sort("discovered_at", -1).limit(10):
        j["_id"] = str(j["_id"])
        if j.get("discovered_at") and hasattr(j["discovered_at"], "isoformat"):
            j["discovered_at"] = j["discovered_at"].isoformat()
        recent_jobs.append(j)

    recent_matches = []
    pipeline = [
        {"$sort": {"created_at": -1}},
        {"$limit": 10},
        {
            "$lookup": {
                "from": "jobs",
                "localField": "job_id",
                "foreignField": "_id",
                "as": "job",
            }
        },
        {"$unwind": "$job"},
    ]
    async for m in db.job_matches.aggregate(pipeline):
        m["_id"] = str(m["_id"])
        m["user_id"] = str(m["user_id"])
        m["job_id"] = str(m["job_id"])
        m["job"]["_id"] = str(m["job"]["_id"])
        recent_matches.append(m)

    return {
        "recent_jobs": recent_jobs,
        "recent_matches": recent_matches,
    }


@router.get("/workflows")
async def list_workflows(admin_id: str = Depends(require_admin)):
    db = get_db()
    runs = []
    async for r in db.workflow_runs.find({}).sort("started_at", -1).limit(50):
        r["_id"] = str(r["_id"])
        if r.get("user_id"):
            r["user_id"] = str(r["user_id"])
        runs.append(r)
    return {"runs": runs}
