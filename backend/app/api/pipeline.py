from fastapi import APIRouter, Request
import structlog
from app.core.background import spawn_background_task
from app.security.jwt import get_current_user_id
from app.graphs.job_pipeline_graph import job_pipeline

router = APIRouter(prefix="/internal", tags=["internal"])
logger = structlog.get_logger()


@router.post("/trigger-pipeline")
async def trigger_user_pipeline(request: Request):
    """Triggered by macOS launchd scheduler or manual webhook to discover & match jobs."""
    user_id = get_current_user_id(request)

    async def run():
        try:
            logger.info("Executing scheduled job pipeline for user", user_id=user_id)
            result = await job_pipeline.ainvoke({"user_id": user_id})
            logger.info(
                "Scheduled job pipeline finished",
                user_id=user_id,
                discovered=len(result.get("discovered_jobs", [])),
                matches=len(result.get("matches", [])),
            )
        except Exception as e:
            logger.error("Scheduled job pipeline failed", user_id=user_id, error=str(e))

    spawn_background_task(f"internal_trigger_pipeline:{user_id}", run())
    return {
        "ok": True,
        "message": "Job discovery and matching pipeline queued for execution",
        "user_id": user_id,
    }
