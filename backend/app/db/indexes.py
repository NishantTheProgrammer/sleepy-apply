from motor.motor_asyncio import AsyncIOMotorDatabase
import structlog

logger = structlog.get_logger()


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all MongoDB indexes on startup."""

    # users
    await db.users.create_index("discord_id", unique=True)
    await db.users.create_index("role")

    # profiles
    await db.profiles.create_index("user_id", unique=True)

    # user_settings
    await db.user_settings.create_index("user_id", unique=True)

    # jobs
    await db.jobs.create_index("content_hash", unique=True)
    await db.jobs.create_index("is_active")
    await db.jobs.create_index([("title", "text"), ("company", "text"), ("description", "text")])

    # job_matches
    await db.job_matches.create_index([("user_id", 1), ("job_id", 1)], unique=True)
    await db.job_matches.create_index([("user_id", 1), ("compatibility_score", -1)])

    # applications
    await db.applications.create_index([("user_id", 1), ("job_id", 1)], unique=True)
    await db.applications.create_index([("user_id", 1), ("status", 1)])
    await db.applications.create_index("status")

    # resumes
    await db.resumes.create_index([("user_id", 1), ("job_id", 1)])

    # workflow_runs
    await db.workflow_runs.create_index("langgraph_thread_id")
    await db.workflow_runs.create_index([("user_id", 1), ("run_type", 1)])

    # job_sources
    await db.job_sources.create_index("is_active")

    logger.info("MongoDB indexes created")
