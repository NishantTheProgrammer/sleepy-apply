from fastapi import APIRouter, Request, HTTPException, Depends
from app.db.client import get_db
from app.security.jwt import get_current_user_id
from app.core.config import get_settings
import structlog

router = APIRouter(prefix="/admin", tags=["admin"])
logger = structlog.get_logger()


async def require_admin(request: Request) -> str:
    """Dependency: ensure the current user has the admin role."""
    user_id = get_current_user_id(request)
    db = get_db()
    from bson import ObjectId
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id


@router.get("/stats")
async def get_stats(admin_id: str = Depends(require_admin)):
    """Aggregate stats across the platform."""
    db = get_db()
    users = await db.users.count_documents({"is_active": True})
    jobs = await db.jobs.count_documents({"is_active": True})
    applications = await db.applications.count_documents({})

    # Application status breakdown
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    status_breakdown = {}
    async for doc in db.applications.aggregate(pipeline):
        status_breakdown[doc["_id"]] = doc["count"]

    # Recent workflow runs
    workflows = await db.workflow_runs.count_documents({"status": "running"})

    return {
        "users": users,
        "active_jobs": jobs,
        "total_applications": applications,
        "application_status_breakdown": status_breakdown,
        "active_workflows": workflows,
    }


@router.get("/users")
async def list_users(admin_id: str = Depends(require_admin)):
    db = get_db()
    users = []
    async for u in db.users.find({}, {"__v": 0}):
        u["_id"] = str(u["_id"])
        users.append(u)
    return {"users": users}


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
