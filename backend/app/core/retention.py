from datetime import datetime, timedelta, timezone
from typing import Any
import structlog

from app.db.client import get_db
from app.core.system_logger import log_system_event

logger = structlog.get_logger()

DEFAULT_RETENTION_DAYS = 60  # 2 months


def is_older_than_retention(dt: datetime | None, days: int = DEFAULT_RETENTION_DAYS) -> bool:
    """Return True if a datetime is strictly older than `days` (default 60 days)."""
    if dt is None or not isinstance(dt, datetime):
        return False
    aware_dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return aware_dt < (datetime.now(timezone.utc) - timedelta(days=days))


async def cleanup_old_entries(db: Any = None, days: int = DEFAULT_RETENTION_DAYS) -> dict[str, int]:
    """
    Remove MongoDB entries older than `days` (default: 60 days / 2 months):
    - Jobs where posted_at < cutoff or discovered_at < cutoff
    - Associated job_matches for removed jobs, plus stale job_matches older than cutoff
    - System logs older than cutoff
    - Workflow runs older than cutoff
    """
    if db is None:
        db = get_db()

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # 1. Find old jobs (either posted > 2 months ago or discovered > 2 months ago)
    old_job_query = {
        "$or": [
            {"posted_at": {"$lt": cutoff}},
            {"discovered_at": {"$lt": cutoff}},
        ]
    }
    old_job_ids = [
        doc["_id"]
        async for doc in db.jobs.find(old_job_query, {"_id": 1})
    ]

    deleted_job_matches = 0
    if old_job_ids:
        res_m = await db.job_matches.delete_many({"job_id": {"$in": old_job_ids}})
        deleted_job_matches += res_m.deleted_count

    res_jobs = await db.jobs.delete_many(old_job_query)

    # Also remove any stale job_matches older than cutoff
    res_stale_matches = await db.job_matches.delete_many({"matched_at": {"$lt": cutoff}})
    deleted_job_matches += res_stale_matches.deleted_count

    # 2. Remove old system logs & workflow runs
    res_logs = await db.system_logs.delete_many({"timestamp": {"$lt": cutoff}})
    res_workflows = await db.workflow_runs.delete_many({"started_at": {"$lt": cutoff}})

    summary = {
        "retention_days": days,
        "jobs_removed": res_jobs.deleted_count,
        "job_matches_removed": deleted_job_matches,
        "system_logs_removed": res_logs.deleted_count,
        "workflow_runs_removed": res_workflows.deleted_count,
    }

    total_removed = (
        summary["jobs_removed"]
        + summary["job_matches_removed"]
        + summary["system_logs_removed"]
        + summary["workflow_runs_removed"]
    )
    if total_removed > 0:
        logger.info("Retention cleanup removed entries older than 2 months", **summary)
        await log_system_event(
            level="INFO",
            category="system",
            message=(
                f"2-month retention cleanup: removed {summary['jobs_removed']} jobs, "
                f"{summary['job_matches_removed']} matches, {summary['system_logs_removed']} logs, "
                f"{summary['workflow_runs_removed']} workflow runs."
            ),
            details=summary,
        )

    return summary
