import asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase
import structlog

logger = structlog.get_logger()


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all MongoDB indexes concurrently on startup."""
    index_tasks = [
        # users
        db.users.create_index("discord_id", unique=True),
        db.users.create_index("role"),

        # profiles
        db.profiles.create_index("user_id", unique=True),

        # user_settings
        db.user_settings.create_index("user_id", unique=True),

        # jobs
        db.jobs.create_index("content_hash", unique=True),
        db.jobs.create_index("is_active"),
        db.jobs.create_index("source"),
        db.jobs.create_index("is_remote"),
        db.jobs.create_index([("discovered_at", -1)]),
        db.jobs.create_index([("source", 1), ("discovered_at", -1)]),
        db.jobs.create_index([("company", 1), ("discovered_at", -1)]),
        db.jobs.create_index("is_delhi_ncr"),
        db.jobs.create_index("delhi_ncr_hub"),
        db.jobs.create_index([("title", "text"), ("company", "text"), ("description", "text")]),

        # job_matches
        db.job_matches.create_index([("user_id", 1), ("job_id", 1)], unique=True),
        db.job_matches.create_index([("user_id", 1), ("compatibility_score", -1)]),

        # applications
        db.applications.create_index([("user_id", 1), ("job_id", 1)], unique=True),
        db.applications.create_index([("user_id", 1), ("status", 1)]),
        db.applications.create_index("status"),

        # resumes
        db.resumes.create_index([("user_id", 1), ("job_id", 1)]),

        # workflow_runs
        db.workflow_runs.create_index("langgraph_thread_id"),
        db.workflow_runs.create_index([("user_id", 1), ("run_type", 1)]),

        # job_sources
        db.job_sources.create_index("is_active"),

        # companies
        db.companies.create_index("name", unique=True),
        db.companies.create_index("grade"),
        db.companies.create_index("is_active"),
        db.companies.create_index("ats_type"),
    ]

    await asyncio.gather(*index_tasks, return_exceptions=True)
    logger.info("MongoDB indexes created")
