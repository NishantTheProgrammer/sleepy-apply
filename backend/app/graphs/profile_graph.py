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

    agent = ProfileCreatorAgent()
    try:
        parsed = await agent.analyze_resume(resume_text, user_settings=user_settings)
        return {"parsed_data": parsed, "error": None}
    except Exception as e:
        logger.error("Failed to parse resume in graph", error=str(e), user_id=user_id)
        return {"error": str(e)}


async def save_profile_node(state: ProfileState) -> ProfileState:
    if state.get("error") or not state.get("parsed_data"):
        return state

    user_id = state["user_id"]
    parsed = state["parsed_data"]
    db = get_db()
    now = datetime.now(timezone.utc)

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
        "updated_at": now,
    }

    await db.profiles.update_one(
        {"user_id": ObjectId(user_id)},
        {"$set": update_fields, "$setOnInsert": {"user_id": ObjectId(user_id), "created_at": now}},
        upsert=True,
    )
    logger.info("Profile successfully saved from resume", user_id=user_id, score=update_fields["completion_score"])
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
