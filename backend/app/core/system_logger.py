import structlog
from datetime import datetime, timezone
from typing import Any
from app.db.client import get_db

logger = structlog.get_logger()


async def log_system_event(
    level: str,
    category: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Persist a structured system event into MongoDB collection 'db.system_logs'.
    Levels: 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    Categories: 'crawler', 'scraper', 'auth', 'matching', 'pipeline', 'system'
    """
    entry = {
        "timestamp": datetime.now(timezone.utc),
        "level": level.upper(),
        "category": category.lower(),
        "message": message,
        "details": details or {},
    }

    try:
        db = get_db()
        res = await db.system_logs.insert_one(entry)
        entry["_id"] = str(res.inserted_id)
    except Exception as e:
        logger.warning("Could not persist system log to MongoDB", error=str(e), msg=message)
        entry["_id"] = "ephemeral"

    # Also forward to structlog
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(f"[{category.upper()}] {message}", **(details or {}))

    return entry


async def get_system_logs(
    page: int = 1,
    limit: int = 50,
    level: str | None = None,
    category: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """Retrieve filtered system logs with statistics."""
    db = get_db()
    skip = (page - 1) * limit
    filter_query: dict[str, Any] = {}

    if level and level != "all":
        filter_query["level"] = level.upper()
    if category and category != "all":
        filter_query["category"] = category.lower()
    if search:
        filter_query["$or"] = [
            {"message": {"$regex": search, "$options": "i"}},
            {"category": {"$regex": search, "$options": "i"}},
            {"details.company": {"$regex": search, "$options": "i"}},
            {"details.url": {"$regex": search, "$options": "i"}},
        ]

    total = await db.system_logs.count_documents(filter_query)
    cursor = db.system_logs.find(filter_query).sort("timestamp", -1).skip(skip).limit(limit)

    logs = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        if doc.get("timestamp") and hasattr(doc["timestamp"], "isoformat"):
            doc["timestamp"] = doc["timestamp"].isoformat()
        logs.append(doc)

    # Compute quick stats
    total_all = await db.system_logs.count_documents({})
    errors_count = await db.system_logs.count_documents({"level": "ERROR"})
    warnings_count = await db.system_logs.count_documents({"level": "WARNING"})
    crawler_count = await db.system_logs.count_documents({"category": "crawler"})

    return {
        "items": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "stats": {
            "total": total_all,
            "errors": errors_count,
            "warnings": warnings_count,
            "crawler": crawler_count,
        },
    }


async def clear_system_logs() -> int:
    """Clear all records from system_logs collection."""
    db = get_db()
    res = await db.system_logs.delete_many({})
    return res.deleted_count

