import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from fastapi.testclient import TestClient
import httpx

from app.agents.discord_bot import (
    DiscordAgent,
    is_valid_token,
    create_bot,
    get_discord_bot,
    is_bot_running,
    start_discord_bot,
    stop_discord_bot,
)
from app.main import app
from app.security.jwt import create_access_token


# ---------------------------------------------------------------------------
# Token Validation Tests
# ---------------------------------------------------------------------------

def test_is_valid_token():
    assert is_valid_token(None) is False
    assert is_valid_token("") is False
    assert is_valid_token("   ") is False
    assert is_valid_token("dev_discord_bot_token") is False
    assert is_valid_token("placeholder") is False
    assert is_valid_token("short.token") is False
    # Typical Discord bot token format
    assert is_valid_token("MTEyMjMzNDQ1NTY2Nzc4ODk5.G7k123.AbCdEfGhIjKlMnOpQrStUvWxYz") is True


# ---------------------------------------------------------------------------
# DiscordAgent Webhook Delivery Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_discord_agent_webhook_success():
    agent = DiscordAgent()
    mock_response = MagicMock(status_code=204)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        res = await agent.send_webhook(
            webhook_url="https://discord.com/api/webhooks/test/123",
            title="Test Title",
            description="Test Description",
            fields=[{"name": "Field 1", "value": "Val 1"}],
        )

        assert res is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["embeds"][0]["title"] == "Test Title"


@pytest.mark.anyio
async def test_discord_agent_webhook_failure():
    agent = DiscordAgent()
    mock_response = MagicMock(status_code=500, text="Internal Server Error")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        res = await agent.send_webhook(
            webhook_url="https://discord.com/api/webhooks/test/123",
            title="Failed Notification",
            description="Should fail gracefully",
        )

        assert res is False


@pytest.mark.anyio
async def test_discord_agent_webhook_exception():
    agent = DiscordAgent()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectTimeout("Connection timed out")
        res = await agent.send_webhook(
            webhook_url="https://discord.com/api/webhooks/test/123",
            title="Timeout Notification",
            description="Should catch exception",
        )

        assert res is False


@pytest.mark.anyio
async def test_discord_agent_webhook_unconfigured():
    agent = DiscordAgent()
    agent.settings.discord_webhook_url = None
    res = await agent.send_webhook(webhook_url=None, title="Unconfigured", description="No url")
    assert res is False


# ---------------------------------------------------------------------------
# DiscordAgent DM Delivery Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_discord_agent_dm_success():
    agent = DiscordAgent()
    valid_token = "MTEyMjMzNDQ1NTY2Nzc4ODk5.G7k123.AbCdEfGhIjKlMnOpQrStUvWxYz"

    with patch.object(agent.settings, "discord_bot_token", valid_token):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            # 1st call for dm channel creation, 2nd call for message posting
            mock_post.side_effect = [
                MagicMock(status_code=200, json=lambda: {"id": "dm_channel_999"}),
                MagicMock(status_code=201, json=lambda: {"id": "msg_888"}),
            ]
            res = await agent.send_dm(
                discord_user_id="123456789012345678",
                title="Direct Alert",
                description="Your application needs confirmation",
            )
            assert res is True
            assert mock_post.call_count == 2


@pytest.mark.anyio
async def test_discord_agent_dm_invalid_token():
    agent = DiscordAgent()
    with patch.object(agent.settings, "discord_bot_token", "dev_discord_bot_token"):
        res = await agent.send_dm(
            discord_user_id="123456789012345678",
            title="Ignored",
            description="Token is placeholder",
        )
        assert res is False


# ---------------------------------------------------------------------------
# Rich Notifications Suite
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_rich_notification_methods():
    agent = DiscordAgent()
    with patch.object(agent, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        # Test notify_application_submitted
        await agent.notify_application_submitted("Backend Engineer", "Stripe", 94)
        mock_send.assert_called_with(
            title="🚀 Application Submitted!",
            description="Sleepy Apply successfully submitted your application for **Backend Engineer** at **Stripe** while you slept.",
            fields=[
                {"name": "Match Score", "value": "**94%**"},
                {"name": "Status", "value": "APPLIED"},
            ],
            color=0x10B981,
            discord_user_id=None,
            webhook_url=None,
        )

        # Test notify_action_required
        await agent.notify_action_required("Staff SWE", "Meta", "recaptcha", "https://apply.meta.com/123")
        assert mock_send.call_args[1]["title"] == "⚠️ Action Required!"
        assert mock_send.call_args[1]["color"] == 0xF59E0B

        # Test notify_new_matches
        await agent.notify_new_matches(5, "Senior Developer", "Shopify", 88)
        assert mock_send.call_args[1]["title"] == "🎯 New Jobs Discovered & Matched!"

        # Test notify_tailored_resume_ready
        await agent.notify_tailored_resume_ready("Lead Architect", "Google", "Lead Cloud Architect", 8)
        assert mock_send.call_args[1]["title"] == "📄 ATS-Tailored Resume Ready!"


# ---------------------------------------------------------------------------
# Interactive Bot Commands Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_bot_command_help():
    bot = create_bot()
    help_cmd = bot.get_command("help")
    assert help_cmd is not None

    ctx = MagicMock()
    ctx.send = AsyncMock()

    await help_cmd(ctx)
    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "Sleepy Apply" in embed.title
    field_names = [f.name for f in embed.fields]
    assert "!status" in field_names
    assert "!jobs" in field_names
    assert "!tailor <job_id>" in field_names
    assert "!apply <job_id>" in field_names
    assert "!profile" in field_names


@pytest.mark.anyio
async def test_bot_command_status_unlinked_user():
    bot = create_bot()
    status_cmd = bot.get_command("status")
    ctx = MagicMock()
    ctx.author.id = 999999999
    ctx.author.name = "TestAuthor"
    ctx.send = AsyncMock()

    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=None)

    with patch("app.agents.discord_bot.get_db", return_value=mock_db):
        await status_cmd(ctx)

    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "Not Linked" in embed.title


@pytest.mark.anyio
async def test_bot_command_status_linked_user():
    bot = create_bot()
    status_cmd = bot.get_command("status")
    ctx = MagicMock()
    ctx.author.id = 123456789
    ctx.author.name = "LinkedUser"
    ctx.send = AsyncMock()

    user_oid = ObjectId()
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value={"_id": user_oid, "discord_username": "LinkedUser"})
    mock_db.profiles.find_one = AsyncMock(return_value={"headline": "Full Stack Engineer", "personal": {"full_name": "Alex Doe"}})
    mock_db.job_matches.count_documents = AsyncMock(return_value=12)
    mock_db.applications.count_documents = AsyncMock(side_effect=[3, 1])

    with patch("app.agents.discord_bot.get_db", return_value=mock_db):
        await status_cmd(ctx)

    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "Alex Doe" in embed.description
    fields_dict = {f.name: f.value for f in embed.fields}
    assert "12" in fields_dict["🎯 Matched Jobs"]
    assert "3" in fields_dict["🚀 Applications"]
    assert "1" in fields_dict["⚠️ Action Items"]


@pytest.mark.anyio
async def test_bot_command_profile():
    bot = create_bot()
    prof_cmd = bot.get_command("profile")
    ctx = MagicMock()
    ctx.author.id = 123456789
    ctx.send = AsyncMock()

    user_oid = ObjectId()
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value={"_id": user_oid, "discord_username": "Alex"})
    mock_db.profiles.find_one = AsyncMock(
        return_value={
            "headline": "Senior Python Engineer",
            "overall_years": 6,
            "personal": {"full_name": "Alex Smith"},
            "skills": ["Python", "FastAPI", "Docker", "PostgreSQL"],
            "target_roles": ["Senior Backend Engineer", "Lead Developer"],
        }
    )

    with patch("app.agents.discord_bot.get_db", return_value=mock_db):
        await prof_cmd(ctx)

    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "Alex Smith" in embed.title
    assert "~6 years" in embed.description
    fields_dict = {f.name: f.value for f in embed.fields}
    assert "Python, FastAPI" in fields_dict["Top Verified Skills"]


@pytest.mark.anyio
async def test_bot_command_tailor():
    bot = create_bot()
    tailor_cmd = bot.get_command("tailor")
    ctx = MagicMock()
    ctx.author.id = 123456789
    ctx.send = AsyncMock()

    user_oid = ObjectId()
    job_oid = ObjectId()
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value={"_id": user_oid})
    mock_db.profiles.find_one = AsyncMock(return_value={"headline": "Backend Engineer"})
    mock_db.jobs.find_one = AsyncMock(return_value={"_id": job_oid, "title": "Staff Backend", "company": "Vercel"})

    mock_tailored_resume = {
        "target_headline": "Staff Backend Engineer - Distributed Systems",
        "matching_skills": ["Python", "AsyncIO", "PostgreSQL"],
        "summary": "Proven track record designing highly resilient backend microservices.",
    }

    with patch("app.agents.discord_bot.get_db", return_value=mock_db):
        with patch("app.agents.resume_builder.ResumeBuilderAgent.build_tailored_resume", new_callable=AsyncMock) as mock_builder:
            mock_builder.return_value = mock_tailored_resume
            await tailor_cmd(ctx, str(job_oid))

    assert ctx.send.call_count >= 2
    last_call_embed = ctx.send.call_args_list[-1][1]["embed"]
    assert "Resume Tailored Successfully!" in last_call_embed.title
    assert "Staff Backend" in last_call_embed.description


@pytest.mark.anyio
async def test_bot_command_apply():
    bot = create_bot()
    apply_cmd = bot.get_command("apply")
    ctx = MagicMock()
    ctx.author.id = 123456789
    ctx.send = AsyncMock()

    user_oid = ObjectId()
    job_oid = ObjectId()
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value={"_id": user_oid})
    mock_db.profiles.find_one = AsyncMock(return_value={"headline": "Backend Engineer"})
    mock_db.jobs.find_one = AsyncMock(return_value={"_id": job_oid, "title": "Staff Backend", "company": "Vercel"})

    with patch("app.agents.discord_bot.get_db", return_value=mock_db):
        with patch("app.agents.job_applier.JobApplierAgent.apply_to_job", new_callable=AsyncMock) as mock_apply:
            mock_apply.return_value = {"status": "APPLIED", "message": "Submitted"}
            await apply_cmd(ctx, str(job_oid))

    assert ctx.send.call_count >= 2
    last_call_embed = ctx.send.call_args_list[-1][1]["embed"]
    assert "Application Submitted!" in last_call_embed.title


# ---------------------------------------------------------------------------
# API Endpoints & Lifespan Tests
# ---------------------------------------------------------------------------

def test_api_discord_endpoints():
    user_id = "650c1f1e1f1e1f1e1f1e1f1e"
    token = create_access_token({"sub": user_id, "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}

    client = TestClient(app, raise_server_exceptions=False)

    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value={"_id": ObjectId(user_id), "discord_id": "11223344", "discord_username": "DiscordDev"})
    mock_db.user_settings.find_one = AsyncMock(return_value={"user_id": ObjectId(user_id), "notification_preferences": {"discord_dm": True, "discord_webhook_url": "https://discord.com/api/webhooks/test"}})

    with patch("app.api.settings.get_db", return_value=mock_db):
        # 1. GET /api/settings/discord-status
        res = client.get("/api/settings/discord-status", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["user_discord_linked"] is True
        assert data["user_discord_username"] == "DiscordDev"

        # 2. POST /api/settings/test-discord
        with patch("app.agents.discord_bot.DiscordAgent.notify_test", new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {"webhook": True, "dm": False}
            res_test = client.post("/api/settings/test-discord", json={"webhook_url": "https://discord.com/api/webhooks/test"}, headers=headers)
            assert res_test.status_code == 200
            test_data = res_test.json()
            assert test_data["ok"] is True
            assert test_data["webhook_sent"] is True


@pytest.mark.anyio
async def test_bot_lifespan_graceful():
    # Calling start with default dev token skips gateway and doesn't crash
    await start_discord_bot()
    assert is_bot_running() is False
    # Stop cleanly executes
    await stop_discord_bot()
