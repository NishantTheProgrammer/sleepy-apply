from typing import TypedDict, Any
from langgraph.graph import StateGraph, START, END
from bson import ObjectId
from datetime import datetime, timezone
import structlog

from app.db.client import get_db
from app.agents.profile_creator import ProfileCreatorAgent
from app.models.settings import UserSettings

logger = structlog.get_logger()


class ProfileState(TypedDict, total=False):
    user_id: str
    resume_text: str
    parsed_data: dict[str, Any]
    error: str | None


async def parse_resume_node(state: ProfileState) -> ProfileState:
    user_id = state["user_id"]
    resume_text = state.get("resume_text", "")
    db = get_db()

    # Load user's settings to resolve their AI provider if set
    settings_doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
    user_settings = UserSettings(**settings_doc) if settings_doc else None
    if not user_settings:
        user_settings = UserSettings(
            user_id=ObjectId(user_id),
            ai_provider="ollama",
            ai_model="llama3.2:latest",
        )

    agent = ProfileCreatorAgent()
    try:
        import asyncio
        parsed = await asyncio.wait_for(
            agent.analyze_resume(resume_text, user_settings=user_settings),
            timeout=55.0,
        )
        return {"parsed_data": parsed, "error": None}
    except Exception as e:
        logger.warning("Resume AI parsing timed out in graph, using fast heuristic parse", error=str(e), user_id=user_id)
        fast_parsed = agent._heuristic_parse(resume_text)
        fast_parsed = agent._normalize_extracted_data(fast_parsed)
        fast_parsed["completion_score"] = agent._calculate_completion_score(fast_parsed)
        return {"parsed_data": fast_parsed, "error": None}


async def save_profile_node(state: ProfileState) -> ProfileState:
    user_id = state["user_id"]
    db = get_db()
    now = datetime.now(timezone.utc)

    if state.get("error") or not state.get("parsed_data"):
        await db.profiles.update_one(
            {"user_id": ObjectId(user_id)},
            {"$set": {"is_analyzing": False, "analysis_error": state.get("error", "Unknown error"), "updated_at": now}},
        )
        return state

    parsed = state["parsed_data"]

    settings_doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
    user_settings = UserSettings(**settings_doc) if settings_doc else None

    from app.agents.screening_agent import ScreeningQAAgent
    screening_agent = ScreeningQAAgent()
    suggested_roles = screening_agent.generate_suggested_roles(parsed)
    try:
        import asyncio
        initial_questions = await asyncio.wait_for(
            screening_agent.generate_screening_questions(
                profile=parsed,
                target_role=suggested_roles[0] if suggested_roles else None,
                user_settings=user_settings,
            ),
            timeout=8.0
        )
    except Exception as q_err:
        logger.warning("Screening questions LLM call timed out, using dynamic fallback", error=str(q_err))
        clean_skills = []
        for v in (parsed.get("skills") or {}).values():
            if isinstance(v, list):
                clean_skills.extend(v)
        initial_questions = screening_agent._generate_dynamic_fallback_questions(
            profile=parsed,
            role=suggested_roles[0] if suggested_roles else "Software Engineer",
            clean_skills=clean_skills
        )

    update_fields = {
        "personal": parsed.get("personal", {}),
        "summary": parsed.get("summary", ""),
        "skills": parsed.get("skills", {}),
        "experience": parsed.get("experience", []),
        "education": parsed.get("education", []),
        "projects": parsed.get("projects", []),
        "achievements": parsed.get("achievements", []),
        "jobPreferences": parsed.get("jobPreferences", {}),
        "job_preferences": parsed.get("job_preferences", {}),
        "additionalInformation": parsed.get("additionalInformation", {}),
        "completion_score": parsed.get("completion_score", 0),
        "missing_fields": parsed.get("missing_fields", []),
        "pending_questions": parsed.get("pending_questions", []),
        "suggested_roles": suggested_roles,
        "screening_questions": initial_questions,
        "is_analyzing": False,
        "analysis_error": None,
        "analyzed_at": now,
        "updated_at": now,
    }

    await db.profiles.update_one(
        {"user_id": ObjectId(user_id)},
        {"$set": update_fields, "$setOnInsert": {"user_id": ObjectId(user_id), "created_at": now}},
        upsert=True,
    )

    # Sync candidate's parsed name to db.users
    full_name = parsed.get("personal", {}).get("fullName") or parsed.get("personal", {}).get("full_name")
    if full_name and full_name.lower() != "candidate":
        await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"name": full_name}})

    logger.info(
        "Profile successfully saved from resume",
        user_id=user_id,
        score=update_fields["completion_score"],
        experiences=len(update_fields["experience"]),
    )

    # Immediately calculate fresh job matches and discover jobs for this new candidate
    import asyncio
    from app.agents.job_matcher import JobMatcherAgent
    from app.graphs.job_pipeline_graph import job_pipeline

    async def match_fresh_jobs():
        try:
            matcher = JobMatcherAgent()
            cursor = db.jobs.find({"is_active": True})
            async for j in cursor:
                await matcher.match_user_and_job(user_id=user_id, job_id=str(j["_id"]), use_ai_reasoning=False)

            # Discover fresh jobs matching the newly detected candidate roles
            await job_pipeline.ainvoke({"user_id": str(user_id)})
        except Exception as err:
            logger.warning("Auto job match after resume save failed", error=str(err))

    asyncio.create_task(match_fresh_jobs())
    return state


def build_profile_graph():
    builder = StateGraph(ProfileState)
    builder.add_node("parse_resume", parse_resume_node)
    builder.add_node("save_profile", save_profile_node)

    builder.add_edge(START, "parse_resume")
    builder.add_edge("parse_resume", "save_profile")
    builder.add_edge("save_profile", END)

    return builder.compile()


profile_pipeline = build_profile_graph()
