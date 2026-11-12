from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Any
import httpx
import structlog
from bson import ObjectId
import discord
from discord.ext import commands

from app.core.config import get_settings
from app.db.client import get_db

logger = structlog.get_logger()

# Global reference for live bot instance & background task
_bot_instance: commands.Bot | None = None
_bot_task: asyncio.Task | None = None


def is_valid_token(token: str | None) -> bool:
    """Check if the provided Discord bot token is a real token, not a dev placeholder or blank."""
    if not token:
        return False
    t = token.strip()
    if t in ("dev_discord_bot_token", "placeholder", "your_discord_bot_token_here", ""):
        return False
    # Discord tokens typically consist of 3 dot-separated base64-like parts
    return len(t) > 20 and "." in t


class AnswerScreeningModal(discord.ui.Modal, title="Answer Application Question"):
    answer_input = discord.ui.TextInput(
        label="Your Answer",
        style=discord.TextStyle.paragraph,
        placeholder="e.g. 30 days notice period, open to early joining",
        required=True,
        max_length=500,
    )

    def __init__(self, question_id: str, question_text: str = ""):
        super().__init__()
        self.question_id = question_id
        self.question_text = question_text
        if question_text:
            truncated = question_text[:42] + "..." if len(question_text) > 45 else question_text
            self.answer_input.label = truncated

    async def on_submit(self, interaction: discord.Interaction):
        answer_val = self.answer_input.value.strip()
        author_id = str(interaction.user.id)
        db = get_db()
        user = await db.users.find_one({"discord_id": author_id})
        if not user:
            await interaction.response.send_message("⚠️ Discord account not linked.", ephemeral=True)
            return

        profile = await db.profiles.find_one({"user_id": user["_id"]})
        now = datetime.now(timezone.utc)
        qa_history = profile.get("qa_history", []) if profile else []
        existing_map = {item.get("id"): item for item in qa_history}
        existing_map[self.question_id] = {
            "id": self.question_id,
            "question": self.question_text or f"Question {self.question_id}",
            "answer": answer_val,
            "category": "screening",
            "answered_at": now.isoformat(),
            "source": "discord_modal",
        }
        screening_qs = profile.get("screening_questions", []) if profile else []
        for sq in screening_qs:
            if sq.get("id") == self.question_id:
                sq["answer"] = answer_val
                sq["answered_at"] = now.isoformat()

        if profile:
            await db.profiles.update_one(
                {"_id": profile["_id"]},
                {"$set": {
                    "qa_history": list(existing_map.values()),
                    "screening_questions": screening_qs,
                    "updated_at": now,
                }}
            )

        # Trigger background re-matching with the new answer
        try:
            from app.agents.job_matcher import JobMatcherAgent
            async def rescore_user_jobs():
                try:
                    matcher = JobMatcherAgent()
                    cursor = db.jobs.find({"is_active": True}).limit(40)
                    async for j in cursor:
                        await matcher.match_user_and_job(user_id=str(user["_id"]), job_id=str(j["_id"]), use_ai_reasoning=False)
                except Exception:
                    pass
            asyncio.create_task(rescore_user_jobs())
        except Exception:
            pass

        await interaction.response.send_message(
            f"✅ <@{author_id}> Answer recorded permanently for future job applications:\n> **{answer_val}**",
            ephemeral=False,
        )


class DiscordAgent:
    """Sends rich notifications and alerts to users via Discord webhook and/or Bot DM."""

    def __init__(self):
        self.settings = get_settings()

    async def send_webhook(
        self,
        webhook_url: str | None,
        title: str,
        description: str,
        fields: list[dict[str, Any]] | None = None,
        color: int = 0x6366F1,  # Indigo
        url: str | None = None,
    ) -> bool:
        """Send an embed message to a Discord webhook."""
        target_url = webhook_url or self.settings.discord_webhook_url
        if not target_url:
            logger.debug("No Discord webhook URL configured, skipping webhook send", title=title)
            return False

        embed: dict[str, Any] = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if url:
            embed["url"] = url
        if fields:
            embed["fields"] = [
                {"name": f["name"], "value": str(f["value"]), "inline": f.get("inline", True)}
                for f in fields
            ]

        payload = {
            "username": "Sleepy Apply",
            "embeds": [embed],
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(target_url, json=payload)
                if res.status_code in [200, 204]:
                    logger.info("Discord webhook delivered", title=title)
                    return True
                else:
                    logger.warning("Discord webhook non-200", status=res.status_code, body=res.text)
                    return False
        except Exception as e:
            logger.error("Failed to send Discord webhook", error=str(e))
            return False

    async def send_dm(
        self,
        discord_user_id: str,
        title: str,
        description: str,
        fields: list[dict[str, Any]] | None = None,
        color: int = 0x6366F1,
        url: str | None = None,
    ) -> bool:
        """Send a Direct Message embed to a user via their Discord user ID."""
        if not discord_user_id:
            return False

        token = self.settings.discord_bot_token
        if not is_valid_token(token):
            logger.debug("Discord bot token not configured or dev placeholder, skipping DM", user_id=discord_user_id)
            return False

        # Attempt 1: If Gateway Bot instance is connected and ready, use it directly
        global _bot_instance
        if _bot_instance and _bot_instance.is_ready():
            try:
                user = _bot_instance.get_user(int(discord_user_id)) or await _bot_instance.fetch_user(int(discord_user_id))
                if user:
                    discord_embed = discord.Embed(
                        title=title,
                        description=description,
                        color=color,
                        url=url,
                        timestamp=datetime.now(timezone.utc),
                    )
                    discord_embed.set_footer(text="Sleepy Apply • Autonomous Job Search")
                    if fields:
                        for f in fields:
                            discord_embed.add_field(
                                name=f["name"],
                                value=str(f["value"]),
                                inline=f.get("inline", True),
                            )
                    await user.send(embed=discord_embed)
                    logger.info("Discord DM sent via Gateway client", discord_user_id=discord_user_id, title=title)
                    return True
            except Exception as e:
                logger.warning("Gateway DM delivery attempt failed, trying REST API", error=str(e))

        # Attempt 2: Direct Discord REST API v10 via httpx
        try:
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Create DM channel
                dm_res = await client.post(
                    "https://discord.com/api/v10/users/@me/channels",
                    headers=headers,
                    json={"recipient_id": str(discord_user_id)},
                )
                if dm_res.status_code not in (200, 201):
                    logger.warning("Could not open Discord DM channel", status=dm_res.status_code, body=dm_res.text)
                    return False

                channel_id = dm_res.json().get("id")
                if not channel_id:
                    return False

                # 2. Post embed message
                embed: dict[str, Any] = {
                    "title": title,
                    "description": description,
                    "color": color,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "footer": {"text": "Sleepy Apply • Autonomous Job Search"},
                }
                if url:
                    embed["url"] = url
                if fields:
                    embed["fields"] = [
                        {"name": f["name"], "value": str(f["value"]), "inline": f.get("inline", True)}
                        for f in fields
                    ]

                msg_res = await client.post(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    headers=headers,
                    json={"embeds": [embed]},
                )
                if msg_res.status_code in (200, 201):
                    logger.info("Discord DM sent via REST API", discord_user_id=discord_user_id, title=title)
                    return True
                else:
                    logger.warning("Failed to post message to DM channel", status=msg_res.status_code, body=msg_res.text)
                    return False
        except Exception as e:
            logger.error("Error sending Discord DM via REST API", error=str(e))
            return False

    async def send_channel(
        self,
        channel_id: str | None,
        title: str,
        description: str,
        fields: list[dict[str, Any]] | None = None,
        color: int = 0x6366F1,
        url: str | None = None,
        content: str | None = None,
        components: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Send an embed message directly to a Discord server text channel with optional user tagging and interactive buttons."""
        cid = channel_id or self.settings.discord_channel_id
        if not cid:
            return False

        token = self.settings.discord_bot_token
        if not is_valid_token(token):
            return False

        # Try live gateway client first when no custom components needed
        global _bot_instance
        if not components and _bot_instance and _bot_instance.is_ready():
            try:
                ch = _bot_instance.get_channel(int(cid)) or await _bot_instance.fetch_channel(int(cid))
                if ch:
                    discord_embed = discord.Embed(
                        title=title,
                        description=description,
                        color=color,
                        timestamp=datetime.now(timezone.utc),
                    )
                    if url:
                        discord_embed.url = url
                    discord_embed.set_footer(text="Sleepy Apply • Autonomous Job Pipeline")
                    if fields:
                        for f in fields:
                            discord_embed.add_field(
                                name=f["name"],
                                value=str(f["value"]),
                                inline=f.get("inline", True),
                            )
                    await ch.send(content=content, embed=discord_embed)
                    logger.info("Discord channel message sent via Gateway", channel_id=cid, title=title)
                    return True
            except Exception as e:
                logger.warning("Gateway channel message failed, falling back to REST", error=str(e), channel_id=cid)

        # Deliver via REST API with component buttons
        try:
            embed_payload: dict[str, Any] = {
                "title": title,
                "description": description,
                "color": color,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "footer": {"text": "Sleepy Apply • Autonomous Job Pipeline"},
            }
            if url:
                embed_payload["url"] = url
            if fields:
                embed_payload["fields"] = [
                    {"name": f["name"], "value": str(f["value"]), "inline": f.get("inline", True)}
                    for f in fields
                ]
            headers = {"Authorization": f"Bot {token}"}
            msg_payload: dict[str, Any] = {"embeds": [embed_payload]}
            if content:
                msg_payload["content"] = content
            if components:
                msg_payload["components"] = components

            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"https://discord.com/api/v10/channels/{cid}/messages",
                    headers=headers,
                    json=msg_payload,
                )
                if res.status_code in [200, 201]:
                    logger.info("Discord channel message sent via REST API", channel_id=cid, title=title)
                    return True
                else:
                    logger.warning("Failed to post message to channel", status=res.status_code, body=res.text)
                    return False
        except Exception as e:
            logger.error("Error sending Discord channel message via REST API", error=str(e))
            return False

    async def send_notification(
        self,
        title: str,
        description: str,
        fields: list[dict[str, Any]] | None = None,
        color: int = 0x6366F1,
        url: str | None = None,
        discord_user_id: str | None = None,
        webhook_url: str | None = None,
        channel_id: str | None = None,
        content: str | None = None,
    ) -> bool:
        """Deliver notification to target server channel, webhook, or user DM if enabled."""
        sent_any = False

        if discord_user_id and self.settings.discord_enable_dm:
            dm_success = await self.send_dm(
                discord_user_id=discord_user_id,
                title=title,
                description=description,
                fields=fields,
                color=color,
                url=url,
            )
            if dm_success:
                sent_any = True

        webhook_success = await self.send_webhook(
            webhook_url=webhook_url,
            title=title,
            description=description,
            fields=fields,
            color=color,
            url=url,
        )
        if webhook_success:
            sent_any = True

        target_channel = channel_id or self.settings.discord_channel_id
        if target_channel:
            ch_success = await self.send_channel(
                channel_id=target_channel,
                title=title,
                description=description,
                fields=fields,
                color=color,
                url=url,
                content=content,
            )
            if ch_success:
                sent_any = True

        return sent_any

    async def notify_admin_crawl(
        self,
        crawled_count: int,
        source_breakdown: dict[str, int] | None = None,
        checkpoint_summary: str = "",
    ) -> bool:
        """Post crawling & source ingestion updates to #admin channel."""
        cid = self.settings.discord_channel_admin or self.settings.discord_channel_id
        sources_str = ", ".join(f"{k}: {v}" for k, v in (source_breakdown or {}).items()) or "Delhi NCR ATS, Naukri, LinkedIn"
        fields = [
            {"name": "Openings Crawled", "value": f"**{crawled_count}** jobs", "inline": True},
            {"name": "Sources", "value": sources_str, "inline": True},
        ]
        if checkpoint_summary:
            fields.append({"name": "Checkpoint", "value": checkpoint_summary, "inline": False})

        return await self.send_channel(
            channel_id=cid,
            title="📊 Openings Crawled & Sources Synced",
            description=f"Automated crawler cycle completed. Discovered and indexed **{crawled_count}** openings across feeds.",
            fields=fields,
            color=0x64748B,
        )

    async def notify_admin_matching(
        self,
        jobs_evaluated: int,
        matches_found: int,
        high_score_count: int = 0,
    ) -> bool:
        """Post matching engine run updates to #admin channel."""
        cid = self.settings.discord_channel_admin or self.settings.discord_channel_id
        fields = [
            {"name": "Jobs Evaluated", "value": f"**{jobs_evaluated}**", "inline": True},
            {"name": "Matches Stored", "value": f"**{matches_found}**", "inline": True},
            {"name": "High Match (≥75%)", "value": f"**{high_score_count}**", "inline": True},
        ]
        return await self.send_channel(
            channel_id=cid,
            title="⚙️ Matching Engine Cycle Completed",
            description="Background matching evaluated indexed openings against candidate profile tech stacks.",
            fields=fields,
            color=0x475569,
        )

    async def notify_admin_crawler_paused(
        self,
        breakpoint_rank: int,
        breakpoint_company: str,
        completed_count: int,
        total_companies: int,
        jobs_discovered: int,
        jobs_saved: int,
        captchas_encountered: int = 0,
        next_company: str = "",
    ) -> bool:
        """Post crawler pause & breakpoint summary to #admin channel."""
        cid = self.settings.discord_channel_admin or self.settings.discord_channel_id
        pct = int((completed_count / max(1, total_companies)) * 100)
        fields = [
            {"name": "⏸️ Breakpoint Reached", "value": f"Rank **{breakpoint_rank}** • **{breakpoint_company}**", "inline": False},
            {"name": "Explored Till Now", "value": f"**{completed_count}** / {total_companies} companies ({pct}%)", "inline": True},
            {"name": "Jobs Discovered", "value": f"**{jobs_discovered}**", "inline": True},
            {"name": "Jobs Saved in DB", "value": f"**{jobs_saved}**", "inline": True},
        ]
        if captchas_encountered > 0:
            fields.append({"name": "CAPTCHAs Aborted", "value": f"**{captchas_encountered}**", "inline": True})
        if next_company:
            fields.append({"name": "Ready to Resume At", "value": f"**{next_company}** (Rank {breakpoint_rank + 1})", "inline": False})

        return await self.send_channel(
            channel_id=cid,
            title="⏸️ AI Browser Crawler Paused at Breakpoint",
            description=f"Crawler paused by admin request. Explored **{completed_count}/{total_companies}** companies till now. Breakpoint saved to MongoDB.",
            fields=fields,
            color=0xF59E0B,
        )

    async def notify_application_submitted(
        self,
        job_title: str,
        company: str,
        score: int,
        resume_path: str | None = None,
        discord_user_id: str | None = None,
        webhook_url: str | None = None,
    ) -> bool:
        """Post submission report to #auto-applied channel and tag candidate."""
        cid = self.settings.discord_channel_auto_applied or self.settings.discord_channel_id
        tag_content = f"<@{discord_user_id}>" if discord_user_id else None
        fields = [
            {"name": "Opening", "value": f"**{job_title}** at **{company}**", "inline": False},
            {"name": "Match Score", "value": f"⭐ **{score}%**", "inline": True},
            {"name": "Status", "value": "✅ **APPLIED**", "inline": True},
        ]
        if resume_path:
            fields.append({"name": "Tailored Resume", "value": "DOCX Generated", "inline": True})

        return await self.send_channel(
            channel_id=cid,
            content=tag_content,
            title=f"🚀 Application Submitted: {company}",
            description=f"Sleepy Apply successfully submitted your application for **{job_title}** at **{company}** while you slept.",
            fields=fields,
            color=0x10B981,
        )

    async def notify_action_required(
        self,
        job_title: str,
        company: str,
        action_type: str,
        action_url: str,
        discord_user_id: str | None = None,
        webhook_url: str | None = None,
    ) -> bool:
        cid = self.settings.discord_channel_auto_applied or self.settings.discord_channel_id
        tag_content = f"<@{discord_user_id}>" if discord_user_id else None
        return await self.send_channel(
            channel_id=cid,
            content=tag_content,
            title=f"⚠️ Action Required: {company}",
            description=f"Action needed to complete application for **{job_title}** at **{company}**.",
            fields=[
                {"name": "Action Type", "value": action_type.upper(), "inline": True},
                {"name": "Form Link", "value": f"[Open Application]({action_url})", "inline": True},
            ],
            color=0xF59E0B,
            url=action_url,
        )

    async def notify_apply_issue(
        self,
        job_title: str,
        company: str,
        issue_message: str,
        target_url: str,
        discord_user_id: str | None = None,
    ) -> bool:
        cid = self.settings.discord_channel_auto_applied or self.settings.discord_channel_id
        tag_content = f"<@{discord_user_id}>" if discord_user_id else None
        return await self.send_channel(
            channel_id=cid,
            content=tag_content,
            title=f"⚠️ Application Attention Needed: {company}",
            description=f"Sleepy Apply autofilled candidate details for **{job_title}** at **{company}**, but encountered an item requiring human attention.",
            fields=[
                {"name": "Attention Reason", "value": issue_message[:500], "inline": False},
                {"name": "Career Portal", "value": f"[Open & Complete on Career Portal]({target_url})", "inline": False},
            ],
            color=0xF59E0B,
            url=target_url,
        )

    async def notify_new_matches(
        self,
        count: int,
        top_job_title: str,
        top_company: str,
        top_score: int,
        location: str = "Delhi NCR / Remote",
        matching_skills: list[str] | None = None,
        discord_user_id: str | None = None,
        job_id: str | None = None,
        webhook_url: str | None = None,
    ) -> bool:
        """Post match notifications to #match channel with interactive 1-click action buttons."""
        cid = self.settings.discord_channel_match or self.settings.discord_channel_id
        tag_content = f"<@{discord_user_id}>" if discord_user_id else None
        fields = [
            {"name": "Top Match", "value": f"**{top_job_title}** at **{top_company}**", "inline": False},
            {"name": "Compatibility Score", "value": f"⭐ **{top_score}% Match**", "inline": True},
            {"name": "Location", "value": location, "inline": True},
        ]
        if matching_skills:
            fields.append({"name": "Verified Skills", "value": ", ".join(matching_skills[:6]), "inline": False})

        components = None
        if job_id:
            components = [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 1,
                            "label": "📄 Tailor Resume",
                            "custom_id": f"tailor_action:{job_id}",
                        },
                        {
                            "type": 2,
                            "style": 3,
                            "label": "🚀 Apply Now",
                            "custom_id": f"apply_action:{job_id}",
                        },
                    ],
                }
            ]

        return await self.send_channel(
            channel_id=cid,
            content=tag_content,
            title=f"🎯 New Job Match: {top_job_title} ({top_score}%)",
            description=f"New opening matching candidate profile with **{top_score}%** compatibility.",
            fields=fields,
            color=0x8B5CF6,
            components=components,
        )

    async def notify_tailored_resume_ready(
        self,
        job_title: str,
        company: str,
        headline: str,
        matched_skills_count: int = 0,
        score: int = 0,
        discord_user_id: str | None = None,
        job_id: str | None = None,
        webhook_url: str | None = None,
    ) -> bool:
        """Post resume tailoring report to #tailored channel with 1-click Apply button."""
        cid = self.settings.discord_channel_tailored or self.settings.discord_channel_id
        tag_content = f"<@{discord_user_id}>" if discord_user_id else None
        fields = [
            {"name": "Position", "value": f"**{job_title}** at **{company}**", "inline": False},
            {"name": "Target Headline", "value": headline[:120], "inline": False},
            {"name": "Tailored Score", "value": f"⭐ **{score}%**" if score else "Verified", "inline": True},
            {"name": "Verified Skills", "value": f"**{matched_skills_count}** skills bolded", "inline": True},
        ]
        components = None
        if job_id:
            components = [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 3,
                            "label": "🚀 Apply with this Resume",
                            "custom_id": f"apply_action:{job_id}",
                        },
                    ],
                }
            ]

        return await self.send_channel(
            channel_id=cid,
            content=tag_content,
            title=f"📄 ATS Resume Tailored: {company}",
            description=f"Tailored resume built for **{job_title}** at **{company}** with zero hallucination.",
            fields=fields,
            color=0x3B82F6,
            components=components,
        )

    async def ask_screening_question(
        self,
        question_id: str,
        question_text: str,
        company: str = "",
        job_title: str = "",
        discord_user_id: str | None = None,
    ) -> bool:
        """Post screening form question to #question channel with interactive Answer button."""
        cid = self.settings.discord_channel_question or self.settings.discord_channel_id
        tag_content = f"<@{discord_user_id}>" if discord_user_id else None
        fields = [
            {"name": "Question", "value": f"**{question_text}**", "inline": False},
            {"name": "How to Answer", "value": "Click **Answer Question** below or reply:\n`!answer <your response>`", "inline": False},
        ]
        components = [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 1,
                        "label": "✍️ Answer Question",
                        "custom_id": f"answer_action:{question_id}",
                    },
                ],
            }
        ]
        comp_str = f" to **{company}**" if company else ""
        return await self.send_channel(
            channel_id=cid,
            content=tag_content,
            title="❓ Application Form Question Needed",
            description=f"To submit your application{comp_str}, please answer the following screening question:",
            fields=fields,
            color=0xF59E0B,
            components=components,
        )

    async def notify_test(
        self,
        discord_user_id: str | None = None,
        webhook_url: str | None = None,
    ) -> dict[str, bool]:
        """Test sending to webhook and/or DM and/or server channel."""
        results = {"webhook": False, "dm": False, "channel": False}
        title = "🧪 Sleepy Apply Discord Connection Verified"
        desc = "Your Sleepy Apply Discord notification integration is functioning properly!"
        fields = [
            {"name": "Timestamp", "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")},
            {"name": "Bot Status", "value": "Connected & Ready" if is_bot_running() else "REST/Webhook Active"},
        ]

        if webhook_url or self.settings.discord_webhook_url:
            results["webhook"] = await self.send_webhook(
                webhook_url=webhook_url,
                title=title,
                description=desc,
                fields=fields,
                color=0x10B981,
            )

        if discord_user_id and self.settings.discord_enable_dm:
            results["dm"] = await self.send_dm(
                discord_user_id=discord_user_id,
                title=title,
                description=desc,
                fields=fields,
                color=0x10B981,
            )

        if self.settings.discord_channel_id:
            results["channel"] = await self.send_channel(
                channel_id=self.settings.discord_channel_id,
                title=title,
                description=desc,
                fields=fields,
                color=0x10B981,
            )

        return results


# ---------------------------------------------------------------------------
# Interactive SleepyDiscordBot Implementation
# ---------------------------------------------------------------------------

def create_bot() -> commands.Bot:
    """Factory to instantiate SleepyDiscordBot with proper intents and registered commands."""
    intents = discord.Intents.default()
    try:
        intents.message_content = True
    except Exception:
        pass

    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    async def get_candidate(ctx: commands.Context) -> tuple[dict | None, dict | None]:
        """Lookup candidate User and Profile in MongoDB by Discord Author ID."""
        try:
            db = get_db()
        except Exception:
            return None, None

        discord_id = str(ctx.author.id)
        user = await db.users.find_one({"discord_id": discord_id})
        if not user:
            return None, None

        profile = await db.profiles.find_one({"user_id": user["_id"]})
        return user, profile

    @bot.event
    async def on_ready():
        logger.info("Discord bot online", bot_user=str(bot.user), bot_id=bot.user.id if bot.user else None)

    @bot.event
    async def on_command_error(ctx: commands.Context, error: Exception):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"⚠️ Missing argument: `{error.param.name}`. Type `!help` for command usage.")
        elif isinstance(error, commands.CommandNotFound):
            pass
        else:
            logger.error("Discord bot command execution error", command=ctx.command.name if ctx.command else "unknown", error=str(error))
            await ctx.send(f"⚠️ Error executing command: {str(error)[:150]}")

    @bot.event
    async def on_interaction(interaction: discord.Interaction):
        """Handle interactive component buttons and modal submissions from Discord channels."""
        # Note: modal submissions are handled by their Modal class (e.g. AnswerScreeningModal.on_submit)
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        if not custom_id:
            return

        logger.info("Discord component interaction received", custom_id=custom_id, author_id=interaction.user.id)
        db = get_db()
        discord_id = str(interaction.user.id)
        user = await db.users.find_one({"discord_id": discord_id})

        if not user:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "⚠️ Your Discord account is not linked to any Sleepy Apply profile.\n"
                    "Please log in to your Sleepy Apply web app to link your account.",
                    ephemeral=True,
                )
            return

        # 1. Answer Question Button -> Prompt Discord Modal
        if custom_id.startswith("answer_action:"):
            question_id = custom_id.split(":", 1)[1]
            profile = await db.profiles.find_one({"user_id": user["_id"]})
            q_text = ""
            if profile:
                for sq in profile.get("screening_questions", []):
                    if sq.get("id") == question_id:
                        q_text = sq.get("question", "")
                        break
            modal = AnswerScreeningModal(question_id=question_id, question_text=q_text)
            await interaction.response.send_modal(modal)
            return

        # 2. Tailor Resume Button -> Run ResumeBuilderAgent & broadcast to #tailored
        if custom_id.startswith("tailor_action:"):
            job_id = custom_id.split(":", 1)[1]
            await interaction.response.defer(ephemeral=False)

            try:
                job_oid = ObjectId(job_id)
                job = await db.jobs.find_one({"_id": job_oid})
            except Exception:
                job = None

            if not job:
                await interaction.followup.send(f"❌ Job not found with ID `{job_id}`.")
                return

            job_title = job.get("title", "Role")
            company = job.get("company", "Company")

            from app.agents.resume_builder import ResumeBuilderAgent
            builder = ResumeBuilderAgent()

            try:
                tailored = await builder.build_tailored_resume(user_id=str(user["_id"]), job_id=job_id)
                if not tailored:
                    await interaction.followup.send(
                        f"❌ Failed to generate tailored resume for **{job_title}** at **{company}**."
                    )
                    return

                content = tailored.get("content", {})
                headline = content.get("target_headline") or job_title
                matched_skills = content.get("matching_skills", [])
                score = content.get("compatibility_score", 0)

                agent = DiscordAgent()
                await agent.notify_tailored_resume_ready(
                    job_title=job_title,
                    company=company,
                    headline=headline,
                    matched_skills_count=len(matched_skills),
                    score=score,
                    discord_user_id=discord_id,
                    job_id=job_id,
                )

                cid_tailored = agent.settings.discord_channel_tailored
                chan_ref = f"<#{cid_tailored}>" if cid_tailored else "#tailored"
                await interaction.followup.send(
                    f"✅ <@{discord_id}> Tailored resume successfully generated for **{job_title}** at **{company}**!\n"
                    f"View full breakdown and 1-click apply button in {chan_ref}."
                )
            except Exception as e:
                logger.error("Error executing Discord tailor action", error=str(e), job_id=job_id)
                await interaction.followup.send(f"❌ Error tailoring resume: {str(e)[:150]}")
            return

        # 3. Apply Now Button -> Run JobApplierAgent & broadcast to #auto-applied
        if custom_id.startswith("apply_action:"):
            job_id = custom_id.split(":", 1)[1]
            await interaction.response.defer(ephemeral=False)

            try:
                job_oid = ObjectId(job_id)
                job = await db.jobs.find_one({"_id": job_oid})
            except Exception:
                job = None

            if not job:
                await interaction.followup.send(f"❌ Job not found with ID `{job_id}`.")
                return

            job_title = job.get("title", "Role")
            company = job.get("company", "Company")

            from app.agents.job_applier import JobApplierAgent
            applier = JobApplierAgent()

            try:
                result = await applier.apply_to_job(user_id=str(user["_id"]), job_id=job_id, force=True)
                status = result.get("status") if isinstance(result, dict) else getattr(result, "status", "UNKNOWN")

                agent = DiscordAgent()
                cid_applied = agent.settings.discord_channel_auto_applied
                chan_ref = f"<#{cid_applied}>" if cid_applied else "#auto-applied"

                if status == "APPLIED":
                    await interaction.followup.send(
                        f"🚀 <@{discord_id}> Application submitted for **{job_title}** at **{company}**!\n"
                        f"Logged in {chan_ref}."
                    )
                elif status == "REQUIRES_USER_ACTION":
                    app_url = job.get("application_url", "")
                    link_text = f" [Open Application Form]({app_url})" if app_url else ""
                    await interaction.followup.send(
                        f"⚠️ <@{discord_id}> Action required to finalize application for **{job_title}** at **{company}**:{link_text}"
                    )
                else:
                    reason = (
                        (result.get("failure_reason") if isinstance(result, dict) else None)
                        or (result.get("reason") if isinstance(result, dict) else None)
                        or getattr(result, "message", None)
                        or "Application could not be completed"
                    )
                    await interaction.followup.send(
                        f"❌ Could not apply to **{job_title}** at **{company}**: {reason}"
                    )
            except Exception as e:
                logger.error("Error executing Discord apply action", error=str(e), job_id=job_id)
                await interaction.followup.send(f"❌ Error during application submission: {str(e)[:150]}")
            return

    @bot.command(name="help")
    async def help_command(ctx: commands.Context):
        """Displays all available Sleepy Apply bot commands."""
        embed = discord.Embed(
            title="🤖 Sleepy Apply • Discord Assistant",
            description="Control your autonomous job search pipeline directly from Discord.",
            color=0x6366F1,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="!status",
            value="View your current pipeline status, profile health, and application counts.",
            inline=False,
        )
        embed.add_field(
            name="!jobs",
            value="List your top 5 matched job openings with compatibility scores.",
            inline=False,
        )
        embed.add_field(
            name="!tailor <job_id>",
            value="Generate an ATS-optimized, hallucination-free tailored resume for a job.",
            inline=False,
        )
        embed.add_field(
            name="!apply <job_id>",
            value="Submit an application for a specific job immediately.",
            inline=False,
        )
        embed.add_field(
            name="!profile",
            value="Inspect your verified technologies, years of experience, and target roles.",
            inline=False,
        )
        embed.set_footer(text="Sleepy Apply • Apply while you sleep")
        await ctx.send(embed=embed)

    @bot.command(name="status")
    async def status_command(ctx: commands.Context):
        """View profile completion, matches, and application statistics."""
        user, profile = await get_candidate(ctx)
        if not user:
            settings_cfg = get_settings()
            embed = discord.Embed(
                title="⚠️ Discord Account Not Linked",
                description=(
                    f"Your Discord account (**{ctx.author.name}**, ID: `{ctx.author.id}`) is not linked to any Sleepy Apply profile.\n\n"
                    f"Please log in to [Sleepy Apply Dashboard]({settings_cfg.frontend_url}) with Discord to link your account."
                ),
                color=0xF59E0B,
            )
            await ctx.send(embed=embed)
            return

        db = get_db()
        user_id = user["_id"]

        # Fetch statistics
        total_matches = await db.job_matches.count_documents({"user_id": user_id})
        total_applied = await db.applications.count_documents({"user_id": user_id, "status": "APPLIED"})
        action_required = await db.applications.count_documents({"user_id": user_id, "status": "REQUIRES_USER_ACTION"})

        headline = (profile or {}).get("headline") or (profile or {}).get("target_title") or "Software Engineer"
        cand_name = (profile or {}).get("personal", {}).get("full_name") or (profile or {}).get("personal", {}).get("fullName") or user.get("discord_username")

        embed = discord.Embed(
            title="📊 Your Sleepy Apply Status",
            description=f"Candidate Profile: **{cand_name}**\nRole Focus: **{headline}**",
            color=0x10B981,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="🎯 Matched Jobs", value=f"**{total_matches}** discovered", inline=True)
        embed.add_field(name="🚀 Applications", value=f"**{total_applied}** submitted", inline=True)
        embed.add_field(name="⚠️ Action Items", value=f"**{action_required}** pending", inline=True)
        embed.set_footer(text="Type !jobs to see your top matches")
        await ctx.send(embed=embed)

    @bot.command(name="jobs")
    async def jobs_command(ctx: commands.Context):
        """List top 5 matched jobs."""
        user, _ = await get_candidate(ctx)
        if not user:
            await ctx.send("⚠️ Discord account not linked. Please log in at your Sleepy Apply web app.")
            return

        db = get_db()
        user_id = user["_id"]

        # Find top 5 job matches sorted by score
        matches_cursor = db.job_matches.find({"user_id": user_id}).sort("compatibility_score", -1).limit(5)
        matches = await matches_cursor.to_list(length=5)

        embed = discord.Embed(
            title="🎯 Top Matched Jobs",
            description="Here are the best positions matching your verified skills:",
            color=0x6366F1,
            timestamp=datetime.now(timezone.utc),
        )

        if not matches:
            # Fallback to recent jobs if no matches scored yet
            recent_jobs = await db.jobs.find({}).sort("created_at", -1).limit(5).to_list(length=5)
            if not recent_jobs:
                await ctx.send("ℹ️ No jobs currently indexed. Try running job discovery from your dashboard!")
                return
            for j in recent_jobs:
                jid = str(j["_id"])
                embed.add_field(
                    name=f"🏢 {j.get('title', 'Role')} • {j.get('company', 'Company')}",
                    value=f"**Location:** {j.get('location', 'Remote')}\n`!tailor {jid}` | `!apply {jid}`",
                    inline=False,
                )
        else:
            for m in matches:
                job_doc = await db.jobs.find_one({"_id": m.get("job_id")})
                if not job_doc:
                    continue
                jid = str(job_doc["_id"])
                score = m.get("compatibility_score", 0)
                embed.add_field(
                    name=f"⭐ {score}% Match • {job_doc.get('title', 'Role')} at {job_doc.get('company', 'Company')}",
                    value=f"**Location:** {job_doc.get('location', 'Remote')}\n`!tailor {jid}` | `!apply {jid}`",
                    inline=False,
                )

        embed.set_footer(text="Use !tailor <job_id> or !apply <job_id>")
        await ctx.send(embed=embed)

    @bot.command(name="tailor")
    async def tailor_command(ctx: commands.Context, job_id: str):
        """Tailor resume for a specific job."""
        user, _ = await get_candidate(ctx)
        if not user:
            await ctx.send("⚠️ Discord account not linked. Please log in at your Sleepy Apply web app.")
            return

        clean_id = job_id.strip("<>")
        try:
            oid = ObjectId(clean_id)
        except Exception:
            await ctx.send(f"❌ Invalid Job ID: `{job_id}`. Please copy a valid Job ID from `!jobs`.")
            return

        db = get_db()
        job = await db.jobs.find_one({"_id": oid})
        if not job:
            await ctx.send(f"❌ Job not found with ID `{clean_id}`.")
            return

        await ctx.send(f"⏳ Tailoring your resume for **{job.get('title')}** at **{job.get('company')}**…")

        from app.agents.resume_builder import ResumeBuilderAgent
        builder = ResumeBuilderAgent()

        try:
            tailored = await builder.build_tailored_resume(user_id=str(user["_id"]), job_id=clean_id)
            if not tailored:
                await ctx.send("❌ Failed to generate tailored resume. Please verify your profile completeness.")
                return

            matching_skills = tailored.get("matching_skills", [])
            skills_preview = ", ".join(matching_skills[:6]) if matching_skills else "None explicitly matched"
            headline = tailored.get("target_headline", job.get("title"))

            embed = discord.Embed(
                title="✅ Resume Tailored Successfully!",
                description=f"Tailored for **{job.get('title')}** at **{job.get('company')}**",
                color=0x10B981,
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Target Headline", value=headline, inline=False)
            embed.add_field(name="Verified Matching Skills", value=skills_preview, inline=False)
            embed.add_field(
                name="Summary Preview",
                value=(tailored.get("summary") or "")[:250] + "…",
                inline=False,
            )
            embed.set_footer(text=f"Ready to apply! Type !apply {clean_id}")
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error("Error during Discord !tailor execution", error=str(e))
            await ctx.send(f"❌ Error during resume tailoring: {str(e)[:150]}")

    @bot.command(name="apply")
    async def apply_command(ctx: commands.Context, job_id: str):
        """Submit an application for a specific job."""
        user, _ = await get_candidate(ctx)
        if not user:
            await ctx.send("⚠️ Discord account not linked. Please log in at your Sleepy Apply web app.")
            return

        clean_id = job_id.strip("<>")
        try:
            oid = ObjectId(clean_id)
        except Exception:
            await ctx.send(f"❌ Invalid Job ID: `{job_id}`. Please copy a valid Job ID from `!jobs`.")
            return

        db = get_db()
        job = await db.jobs.find_one({"_id": oid})
        if not job:
            await ctx.send(f"❌ Job not found with ID `{clean_id}`.")
            return

        await ctx.send(f"⏳ Submitting application for **{job.get('title')}** at **{job.get('company')}**…")

        from app.agents.job_applier import JobApplierAgent
        applier = JobApplierAgent()

        try:
            result = await applier.apply_to_job(user_id=str(user["_id"]), job_id=clean_id, force=True)
            status = result.get("status") if isinstance(result, dict) else getattr(result, "status", "UNKNOWN")

            if status == "APPLIED":
                embed = discord.Embed(
                    title="🚀 Application Submitted!",
                    description=f"Successfully applied to **{job.get('title')}** at **{job.get('company')}**!",
                    color=0x10B981,
                )
                await ctx.send(embed=embed)
            elif status == "REQUIRES_USER_ACTION":
                app_url = job.get("application_url", "")
                embed = discord.Embed(
                    title="⚠️ Action Required!",
                    description=f"Action required to finalize application for **{job.get('title')}** at **{job.get('company')}**.",
                    color=0xF59E0B,
                )
                if app_url:
                    embed.add_field(name="Complete Application", value=f"[Open Form Link]({app_url})", inline=False)
                await ctx.send(embed=embed)
            else:
                reason = result.get("failure_reason") or result.get("reason") or "Application could not be completed"
                embed = discord.Embed(
                    title="❌ Application Status",
                    description=f"Status: **{status}**\nReason: {reason}",
                    color=0xEF4444,
                )
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error("Error during Discord !apply execution", error=str(e))
            await ctx.send(f"❌ Application error: {str(e)[:150]}")

    @bot.command(name="profile")
    async def profile_command(ctx: commands.Context):
        """Displays verified profile overview."""
        user, profile = await get_candidate(ctx)
        if not user:
            await ctx.send("⚠️ Discord account not linked. Please log in at your Sleepy Apply web app.")
            return

        if not profile:
            await ctx.send("ℹ️ No candidate profile saved yet. Please complete your profile on the web dashboard.")
            return

        cand_name = profile.get("personal", {}).get("full_name") or profile.get("personal", {}).get("fullName") or user.get("discord_username")
        headline = profile.get("headline") or profile.get("target_title") or "Software Engineer"
        overall_years = profile.get("total_years_experience") or profile.get("overall_years") or 0

        # Primary skills
        skills = profile.get("skills", [])
        if isinstance(skills, list):
            skills_str = ", ".join(str(s) for s in skills[:10])
        elif isinstance(skills, dict):
            flat = []
            for v in skills.values():
                if isinstance(v, list):
                    flat.extend(str(item) for item in v)
            skills_str = ", ".join(flat[:10])
        else:
            skills_str = "Not listed"

        embed = discord.Embed(
            title=f"👤 Candidate Profile • {cand_name}",
            description=f"**Headline:** {headline}\n**Experience:** ~{overall_years} years",
            color=0x6366F1,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Top Verified Skills", value=skills_str or "None specified", inline=False)
        target_roles = profile.get("target_roles") or []
        if target_roles:
            embed.add_field(name="Target Roles", value=", ".join(target_roles[:4]), inline=False)

        await ctx.send(embed=embed)

    @bot.command(name="answer")
    async def answer_command(ctx: commands.Context, *, response_text: str):
        """Answer a screening form question and store it permanently against the candidate profile."""
        user, profile = await get_candidate(ctx)
        if not user:
            await ctx.send("⚠️ Discord account not linked. Please log in at Sleepy Apply.")
            return

        db = get_db()
        now = datetime.now(timezone.utc)
        clean_ans = response_text.strip()
        if not clean_ans:
            await ctx.send("⚠️ Please provide an answer: `!answer <your response>`")
            return

        screening_qs = profile.get("screening_questions", []) if profile else []
        pending_q = None
        for q in screening_qs:
            if not q.get("answer"):
                pending_q = q
                break

        if not pending_q and screening_qs:
            pending_q = screening_qs[-1]

        q_id = pending_q.get("id") if pending_q else f"q_{int(now.timestamp())}"
        q_text = pending_q.get("question") if pending_q else "Screening Question"

        qa_history = profile.get("qa_history", []) if profile else []
        existing_map = {item.get("id"): item for item in qa_history}
        existing_map[q_id] = {
            "id": q_id,
            "question": q_text,
            "answer": clean_ans,
            "category": "screening",
            "answered_at": now.isoformat(),
            "source": "discord_channel",
        }
        updated_qa = list(existing_map.values())

        for sq in screening_qs:
            if sq.get("id") == q_id:
                sq["answer"] = clean_ans
                sq["answered_at"] = now.isoformat()

        if profile:
            await db.profiles.update_one(
                {"_id": profile["_id"]},
                {"$set": {
                    "qa_history": updated_qa,
                    "screening_questions": screening_qs,
                    "updated_at": now,
                }}
            )

        # Trigger background re-matching
        try:
            from app.agents.job_matcher import JobMatcherAgent
            async def rescore_user_jobs():
                try:
                    matcher = JobMatcherAgent()
                    cursor = db.jobs.find({"is_active": True}).limit(40)
                    async for j in cursor:
                        await matcher.match_user_and_job(user_id=str(user["_id"]), job_id=str(j["_id"]), use_ai_reasoning=False)
                except Exception:
                    pass
            asyncio.create_task(rescore_user_jobs())
        except Exception:
            pass

        embed = discord.Embed(
            title="✅ Answer Saved Permanently!",
            description=f"<@{ctx.author.id}>, your answer has been saved to your profile.",
            color=0x10B981,
            timestamp=now,
        )
        embed.add_field(name="Question", value=q_text, inline=False)
        embed.add_field(name="Saved Answer", value=clean_ans, inline=False)
        embed.set_footer(text="Sleepy Apply will reuse this answer automatically for all future applications!")
        await ctx.send(embed=embed)

    return bot


def get_discord_bot() -> commands.Bot:
    """Return singleton instance of SleepyDiscordBot."""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = create_bot()
    return _bot_instance


def is_bot_running() -> bool:
    """Check if Discord gateway bot is currently online and connected."""
    global _bot_instance
    return bool(_bot_instance and _bot_instance.is_ready() and not _bot_instance.is_closed())


async def start_discord_bot() -> None:
    """Start Discord bot in the background during FastAPI lifespan."""
    global _bot_instance, _bot_task
    settings = get_settings()
    token = settings.discord_bot_token

    if not is_valid_token(token):
        logger.info(
            "Discord bot token is unset or dev placeholder. Bot Gateway skipped; Webhook and REST delivery remain active."
        )
        return

    bot = get_discord_bot()

    async def _runner():
        try:
            logger.info("Connecting Discord bot to gateway...")
            await bot.start(token)
        except discord.LoginFailure:
            logger.warning("Discord bot login failed: invalid bot token provided.")
        except discord.PrivilegedIntentsRequired:
            logger.warning("Discord bot privileged intents required: check Discord Developer Portal.")
        except asyncio.CancelledError:
            logger.info("Discord bot runner task cancelled.")
        except Exception as e:
            logger.warning("Discord bot connection error", error=str(e))

    _bot_task = asyncio.create_task(_runner())


async def stop_discord_bot() -> None:
    """Cleanly close Discord bot during FastAPI shutdown."""
    global _bot_instance, _bot_task
    if _bot_instance and not _bot_instance.is_closed():
        try:
            logger.info("Closing Discord bot gateway connection...")
            await _bot_instance.close()
        except Exception as e:
            logger.warning("Error closing Discord bot", error=str(e))

    if _bot_task and not _bot_task.done():
        _bot_task.cancel()
        try:
            await _bot_task
        except asyncio.CancelledError:
            pass
