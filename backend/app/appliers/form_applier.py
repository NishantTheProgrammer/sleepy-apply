import httpx
import structlog
from .base import BaseJobApplier, ApplicationResult

logger = structlog.get_logger()


class FormJobApplier(BaseJobApplier):
    applier_name: str = "form_applier"

    async def apply(
        self,
        job: dict,
        user: dict,
        resume: dict,
        profile: dict,
    ) -> ApplicationResult:
        """Attempts to apply for the given job.

        Detects if CAPTCHA or external portal login is required,
        or performs autonomous submission.
        """
        app_url = job.get("application_url") or job.get("source_url")
        if not app_url:
            return ApplicationResult(
                success=False,
                status="FAILED",
                message="No application URL provided for job",
            )

        # Detect portals that always require manual auth or complex anti-bot CAPTCHA
        manual_keywords = ["myworkdayjobs.com", "taleo.net", "brassring.com", "icims.com"]
        if any(kw in app_url.lower() for kw in manual_keywords):
            logger.info("External ATS login detected, flagging for user action", url=app_url)
            return ApplicationResult(
                success=False,
                status="REQUIRES_USER_ACTION",
                action_type="manual_form",
                message=f"Manual login required on company career portal: {app_url}",
                details={"url": app_url},
            )

        try:
            # Execute browser-driven form autofill (Dry-run mode: fills all fields and stops before submit)
            from app.agents.browser_form_filler import form_filler

            fill_res = await form_filler.fill_application_form(
                job=job,
                user=user,
                profile=profile,
                resume=resume,
                dry_run=True,
            )

            if fill_res.success:
                return ApplicationResult(
                    success=True,
                    status="FORM_FILLED_READY",
                    action_type="review_ready",
                    message=fill_res.message,
                    details=fill_res.to_dict(),
                )
            else:
                return ApplicationResult(
                    success=False,
                    status="FAILED",
                    message=fill_res.message,
                    details=fill_res.to_dict(),
                )

        except Exception as e:
            logger.error("Application form autofill failed with error", error=str(e), url=app_url)
            return ApplicationResult(
                success=False,
                status="FAILED",
                message=f"Autofill error: {str(e)}",
                details={"error": str(e)},
            )
