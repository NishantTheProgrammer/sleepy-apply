import httpx
import structlog
from app.core.config import get_settings

logger = structlog.get_logger()


class DiscordAgent:
    """Sends notifications and action requests to users via Discord webhook or bot API."""

    def __init__(self):
        self.settings = get_settings()

    async def send_notification(
        self,
        title: str,
        description: str,
        fields: list[dict[str, str]] | None = None,
        color: int = 0x6366F1,  # Indigo
        url: str | None = None,
    ) -> bool:
        webhook_url = self.settings.discord_webhook_url
        if not webhook_url:
            logger.info("Discord webhook URL not configured, skipping notification", title=title)
            return False

        embed = {
            "title": title,
            "description": description,
            "color": color,
        }
        if url:
            embed["url"] = url
        if fields:
            embed["fields"] = [{"name": f["name"], "value": f["value"], "inline": f.get("inline", True)} for f in fields]

        payload = {
            "username": "Sleepy Apply",
            "embeds": [embed],
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(webhook_url, json=payload)
                if res.status_code in [200, 204]:
                    logger.info("Discord notification sent successfully", title=title)
                    return True
                else:
                    logger.warning("Discord webhook returned non-200", status=res.status_code, body=res.text)
                    return False
        except Exception as e:
            logger.error("Failed to send Discord webhook", error=str(e))
            return False

    async def notify_application_submitted(self, job_title: str, company: str, score: int, resume_path: str | None = None):
        return await self.send_notification(
            title="🚀 Application Submitted!",
            description=f"Sleepy Apply successfully submitted your application for **{job_title}** at **{company}** while you slept.",
            fields=[
                {"name": "Match Score", "value": f"**{score}%**"},
                {"name": "Status", "value": "APPLIED"},
            ],
            color=0x10B981,  # Emerald
        )

    async def notify_action_required(self, job_title: str, company: str, action_type: str, action_url: str):
        return await self.send_notification(
            title="⚠️ Action Required!",
            description=f"Action needed to complete application for **{job_title}** at **{company}**.",
            fields=[
                {"name": "Action Type", "value": action_type.upper()},
                {"name": "Link", "value": f"[Open Application]({action_url})"},
            ],
            color=0xF59E0B,  # Amber
            url=action_url,
        )

    async def notify_new_matches(self, count: int, top_job_title: str, top_company: str, top_score: int):
        return await self.send_notification(
            title="🎯 New Jobs Discovered & Matched!",
            description=f"Discovered **{count}** new matching jobs today.",
            fields=[
                {"name": "Top Match", "value": f"{top_job_title} at {top_company}"},
                {"name": "Compatibility", "value": f"**{top_score}%**"},
            ],
            color=0x8B5CF6,  # Purple
        )
