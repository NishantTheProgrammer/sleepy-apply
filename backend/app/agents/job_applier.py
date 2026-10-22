from datetime import datetime, timezone
import structlog
from bson import ObjectId
from app.db.client import get_db
from app.appliers.form_applier import FormJobApplier
from app.agents.discord_bot import DiscordAgent
from app.models.settings import UserSettings

logger = structlog.get_logger()


class JobApplierAgent:
    """Coordinates job application execution, checks limits & preferences, and applies."""

    def __init__(self):
        self.applier = FormJobApplier()
        self.discord = DiscordAgent()

    async def apply_to_job(
        self,
        user_id: str,
        job_id: str,
        match_id: str | None = None,
        resume_id: str | None = None,
        force: bool = False,
    ) -> dict:
        db = get_db()
        now = datetime.now(timezone.utc)

        user = await db.users.find_one({"_id": ObjectId(user_id)})
        profile = await db.profiles.find_one({"user_id": ObjectId(user_id)})
        job = await db.jobs.find_one({"_id": ObjectId(job_id)})
        settings_doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
        resume = await db.resumes.find_one({"_id": ObjectId(resume_id)}) if resume_id else None

        if not user or not job or not profile:
            raise ValueError("User, profile, or job not found")

        app_prefs = (settings_doc or {}).get("application_preferences", {})
        min_score = int(app_prefs.get("auto_apply_threshold", app_prefs.get("min_compatibility_score", 70)))
        require_confirmation = app_prefs.get("require_confirmation", False)

        # Check match score
        match = await db.job_matches.find_one({"user_id": ObjectId(user_id), "job_id": ObjectId(job_id)})
        score = match.get("compatibility_score", 0) if match else 0
        if not force and score < min_score:
            logger.info("Job match score below threshold, skipping", score=score, threshold=min_score)
            return {"status": "SKIPPED", "reason": f"Score {score} < {min_score}"}

        # Check existing application record
        app_doc = await db.applications.find_one({"user_id": ObjectId(user_id), "job_id": ObjectId(job_id)})
        if not app_doc:
            app_doc = {
                "user_id": ObjectId(user_id),
                "job_id": ObjectId(job_id),
                "match_id": ObjectId(match_id) if match_id else None,
                "resume_id": ObjectId(resume_id) if resume_id else None,
                "status": "DISCOVERED",
                "status_history": [],
                "created_at": now,
                "updated_at": now,
            }
            res = await db.applications.insert_one(app_doc)
            app_doc["_id"] = res.inserted_id

        # Human-in-the-loop: if user requires confirmation, stop here and ask
        if require_confirmation and not force:
            await self._update_status(
                app_doc["_id"],
                "READY_TO_APPLY",
                reason="Waiting for user confirmation before submitting",
            )
            await self.discord.notify_action_required(
                job_title=job.get("title", "Job"),
                company=job.get("company", "Company"),
                action_type="Application Confirmation",
                action_url=job.get("application_url", ""),
            )
            return {"status": "READY_TO_APPLY", "message": "Confirmation requested from user"}

        # Mark as APPLYING
        await self._update_status(app_doc["_id"], "APPLYING")

        # Execute submission
        result = await self.applier.apply(
            job=job,
            user=user,
            resume=resume or {},
            profile=profile,
        )

        if result.status == "APPLIED":
            await self._update_status(app_doc["_id"], "APPLIED", reason=result.message)
            await db.applications.update_one(
                {"_id": app_doc["_id"]},
                {"$set": {"applied_at": now, "application_method": self.applier.applier_name}},
            )
            await self.discord.notify_application_submitted(
                job_title=job.get("title", ""),
                company=job.get("company", ""),
                score=score,
            )
        elif result.status == "REQUIRES_USER_ACTION":
            action_info = {
                "type": result.action_type or "manual_form",
                "description": result.message,
                "created_at": now,
            }
            await db.applications.update_one(
                {"_id": app_doc["_id"]},
                {"$set": {"requires_action": action_info}},
            )
            await self._update_status(app_doc["_id"], "REQUIRES_USER_ACTION", reason=result.message)
            await self.discord.notify_action_required(
                job_title=job.get("title", ""),
                company=job.get("company", ""),
                action_type=result.action_type or "manual_form",
                action_url=job.get("application_url", ""),
            )
        else:
            await self._update_status(app_doc["_id"], "FAILED", reason=result.message)
            await db.applications.update_one(
                {"_id": app_doc["_id"]},
                {"$set": {"failure_reason": result.message, "failure_details": result.details}},
            )

        updated_app = await db.applications.find_one({"_id": app_doc["_id"]})
        return updated_app

    async def _update_status(self, app_id: ObjectId, new_status: str, reason: str | None = None):
        db = get_db()
        now = datetime.now(timezone.utc)
        entry = {"status": new_status, "timestamp": now, "reason": reason}
        await db.applications.update_one(
            {"_id": app_id},
            {
                "$set": {"status": new_status, "updated_at": now},
                "$push": {"status_history": entry},
            },
        )
