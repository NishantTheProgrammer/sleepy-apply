from typing import TypedDict, Any
from langgraph.graph import StateGraph, START, END
from bson import ObjectId
import structlog

from app.db.client import get_db
from app.agents.job_fetcher import JobFetcherAgent
from app.agents.job_enrichment import JobEnrichmentAgent
from app.agents.job_matcher import JobMatcherAgent
from app.agents.discord_bot import DiscordAgent
from app.models.settings import UserSettings
from app.pipeline.role_search import get_unique_user_selected_roles

logger = structlog.get_logger()


class JobPipelineState(TypedDict, total=False):
    user_id: str | None
    custom_keywords: list[str] | None
    custom_urls: list[str] | None
    discovered_jobs: list[dict]
    enriched_jobs: list[dict]
    matches: list[dict]
    error: str | None


async def fetch_jobs_node(state: JobPipelineState) -> JobPipelineState:
    agent = JobFetcherAgent()
    try:
        db = get_db()
        # Retrieve unique roles selected by the user (or all active users if user_id is None)
        user_roles = await get_unique_user_selected_roles(db, user_id=state.get("user_id"))

        if state.get("custom_keywords"):
            raw_ck = state["custom_keywords"]
            if isinstance(raw_ck, str):
                raw_ck = [raw_ck]
            for k in raw_ck:
                if k and k not in user_roles:
                    user_roles.append(k)

        new_jobs = await agent.fetch_and_store_jobs(
            custom_urls=state.get("custom_urls"),
            keywords=user_roles if user_roles else None,
        )
        return {"discovered_jobs": new_jobs}
    except Exception as e:
        logger.error("Job fetch node failed", error=str(e))
        return {"discovered_jobs": [], "error": str(e)}


async def enrich_jobs_node(state: JobPipelineState) -> JobPipelineState:
    db = get_db()
    enrichment_agent = JobEnrichmentAgent()
    enriched = []

    # Get user settings if user_id is provided
    user_settings = None
    if state.get("user_id"):
        settings_doc = await db.user_settings.find_one({"user_id": ObjectId(state["user_id"])})
        if settings_doc:
            user_settings = UserSettings(**settings_doc)

    # Process unenriched jobs (up to 20 per cycle)
    cursor = db.jobs.find({"enriched": False}).limit(20)
    async for job in cursor:
        try:
            res = await enrichment_agent.enrich_job(str(job["_id"]), user_settings=user_settings)
            enriched.append(res)
        except Exception as e:
            logger.warning("Failed to enrich job", job_id=str(job["_id"]), error=str(e))

    return {"enriched_jobs": enriched}


async def match_jobs_node(state: JobPipelineState) -> JobPipelineState:
    db = get_db()
    matcher = JobMatcherAgent()
    matches = []

    # Determine which users to match
    target_user_ids = []
    if state.get("user_id"):
        target_user_ids.append(state["user_id"])
    else:
        cursor = db.users.find({"is_active": True})
        async for u in cursor:
            target_user_ids.append(str(u["_id"]))

    for uid in target_user_ids:
        settings_doc = await db.user_settings.find_one({"user_id": ObjectId(uid)})
        user_settings = UserSettings(**settings_doc) if settings_doc else None

        app_prefs = user_settings.application_preferences if user_settings else None
        threshold = int(getattr(app_prefs, "auto_apply_threshold", getattr(app_prefs, "min_compatibility_score", 60)) if app_prefs else 60)

        # Find active jobs to match
        job_cursor = db.jobs.find({"is_active": True}).sort("discovered_at", -1).limit(250)
        async for j in job_cursor:
            m = await matcher.match_user_and_job(uid, str(j["_id"]), user_settings=user_settings, use_ai_reasoning=False)
            if m and m.get("compatibility_score", 0) >= threshold:
                matches.append(m)

                # Auto-apply if enabled in application preferences
                if app_prefs and getattr(app_prefs, "auto_apply", False):
                    try:
                        from app.graphs.application_graph import application_pipeline
                        import asyncio
                        asyncio.create_task(
                            application_pipeline.ainvoke({
                                "user_id": uid,
                                "job_id": str(j["_id"]),
                                "match_id": str(m.get("_id", "")),
                            })
                        )
                        logger.info("Auto-apply triggered for qualified match", user_id=uid, job_id=str(j["_id"]), score=m.get("compatibility_score"))
                    except Exception as apply_err:
                        logger.error("Failed to trigger auto-apply", error=str(apply_err), user_id=uid, job_id=str(j["_id"]))

    return {"matches": matches}


async def notify_matches_node(state: JobPipelineState) -> JobPipelineState:
    matches = state.get("matches", [])
    if not matches:
        return state

    discord = DiscordAgent()
    db = get_db()
    user_id = state.get("user_id")

    user_doc = None
    if user_id:
        try:
            from bson import ObjectId
            user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
        except Exception:
            user_doc = await db.users.find_one({"_id": user_id})

    discord_id = (user_doc or {}).get("discord_id")

    # Get top match
    top_match = max(matches, key=lambda m: m.get("compatibility_score", 0))
    job = await db.jobs.find_one({"_id": top_match["job_id"]})
    if job:
        await discord.notify_new_matches(
            count=len(matches),
            top_job_title=job.get("title", "Software Engineer"),
            top_company=job.get("company", "Company"),
            top_score=top_match.get("compatibility_score", 0),
            location=job.get("location", "Delhi NCR / Remote"),
            matching_skills=top_match.get("matched_skills", []),
            discord_user_id=discord_id,
        )

    # Broadcast matching completed summary to #admin
    high_scores = len([m for m in matches if m.get("compatibility_score", 0) >= 75])
    await discord.notify_admin_matching(
        jobs_evaluated=len(state.get("enriched_jobs", [])),
        matches_found=len(matches),
        high_score_count=high_scores,
    )

    return state


def build_job_pipeline_graph():
    builder = StateGraph(JobPipelineState)
    builder.add_node("fetch_jobs", fetch_jobs_node)
    builder.add_node("enrich_jobs", enrich_jobs_node)
    builder.add_node("match_jobs", match_jobs_node)
    builder.add_node("notify_matches", notify_matches_node)

    builder.add_edge(START, "fetch_jobs")
    builder.add_edge("fetch_jobs", "enrich_jobs")
    builder.add_edge("enrich_jobs", "match_jobs")
    builder.add_edge("match_jobs", "notify_matches")
    builder.add_edge("notify_matches", END)

    return builder.compile()


job_pipeline = build_job_pipeline_graph()
