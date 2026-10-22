import asyncio
import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.client import connect_db, get_db

logger = structlog.get_logger()


async def seed_jobs_collection(db: AsyncIOMotorDatabase, force_overwrite: bool = False) -> int:
    """Fetch and populate MongoDB jobs collection exclusively with 100% real live postings from active sources."""
    from app.agents.job_fetcher import JobFetcherAgent

    logger.info("Synchronizing real live jobs from active sources (career ATS, LinkedIn, Naukri)...")
    fetcher = JobFetcherAgent()
    new_jobs = await fetcher.fetch_and_store_jobs(source="all")
    logger.info("Real live job synchronization complete", new_jobs_count=len(new_jobs))
    return len(new_jobs)


async def main():
    await connect_db()
    db = get_db()
    count = await seed_jobs_collection(db)
    total = await db.jobs.count_documents({})
    print(f"✅ Real jobs sync complete. Total jobs in db.jobs: {total} (New inserted: {count})")


if __name__ == "__main__":
    asyncio.run(main())
