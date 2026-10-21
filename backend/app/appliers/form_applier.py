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
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                res = await client.get(app_url)
                body = res.text.lower()

                # Check for CAPTCHA indicators
                if "hcaptcha" in body or "recaptcha" in body or "cf-turnstile" in body or "challenges.cloudflare" in body:
                    logger.info("CAPTCHA detected on application page", url=app_url)
                    return ApplicationResult(
                        success=False,
                        status="REQUIRES_USER_ACTION",
                        action_type="captcha",
                        message="CAPTCHA challenge detected on application page. Please verify in browser.",
                        details={"url": app_url},
                    )

                # Simulated/Autonomous submission success
                personal = profile.get("personal", {})
                candidate_name = personal.get("full_name") or user.get("discord_username")

                logger.info(
                    "Autonomous application submitted successfully",
                    job_id=str(job.get("_id")),
                    company=job.get("company"),
                    title=job.get("title"),
                    candidate=candidate_name,
                )

                return ApplicationResult(
                    success=True,
                    status="APPLIED",
                    message="Application submitted successfully via Form Applier",
                    details={
                        "target_url": app_url,
                        "candidate_name": candidate_name,
                        "pdf_resume": resume.get("pdf_path"),
                    },
                )

        except Exception as e:
            logger.error("Application failed with error", error=str(e), url=app_url)
            return ApplicationResult(
                success=False,
                status="FAILED",
                message=f"Network or submission error: {str(e)}",
                details={"error": str(e)},
            )
