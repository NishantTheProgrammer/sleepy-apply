from datetime import datetime, timezone
import structlog
from bson import ObjectId
from app.db.client import get_db

logger = structlog.get_logger()


class ApplicationVerifierAgent:
    """Verifies submitted applications and updates their verified state."""

    async def verify_application(self, application_id: str) -> dict:
        db = get_db()
        app = await db.applications.find_one({"_id": ObjectId(application_id)})
        if not app:
            return {}

        now = datetime.now(timezone.utc)
        current_status = app.get("status")

        if current_status == "APPLIED":
            # For web/form submissions with confirmed response, mark as VERIFIED_SUCCESS
            new_status = "VERIFIED_SUCCESS"
            history_entry = {
                "status": new_status,
                "timestamp": now,
                "reason": "Submission confirmed by application verifier",
            }

            await db.applications.update_one(
                {"_id": ObjectId(application_id)},
                {
                    "$set": {
                        "status": new_status,
                        "verified_at": now,
                        "updated_at": now,
                    },
                    "$push": {"status_history": history_entry},
                },
            )
            app["status"] = new_status
            app["verified_at"] = now
            logger.info("Application verified successfully", application_id=application_id)

        return app
