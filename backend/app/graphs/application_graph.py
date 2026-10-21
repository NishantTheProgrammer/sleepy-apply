from typing import TypedDict, Any
from langgraph.graph import StateGraph, START, END
from bson import ObjectId
import structlog

from app.db.client import get_db
from app.agents.resume_builder import ResumeBuilderAgent
from app.agents.job_applier import JobApplierAgent
from app.agents.app_verifier import ApplicationVerifierAgent
from app.models.settings import UserSettings

logger = structlog.get_logger()


class ApplicationPipelineState(TypedDict, total=False):
    user_id: str
    job_id: str
    match_id: str | None
    resume_id: str | None
    application_id: str | None
    application_result: dict[str, Any]
    error: str | None


async def build_resume_node(state: ApplicationPipelineState) -> ApplicationPipelineState:
    user_id = state["user_id"]
    job_id = state["job_id"]
    db = get_db()

    settings_doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
    user_settings = UserSettings(**settings_doc) if settings_doc else None

    builder = ResumeBuilderAgent()
    try:
        resume_doc = await builder.build_tailored_resume(user_id, job_id, user_settings=user_settings)
        if resume_doc:
            return {"resume_id": str(resume_doc["_id"])}
    except Exception as e:
        logger.error("Resume builder node failed", error=str(e), user_id=user_id, job_id=job_id)
        return {"error": str(e)}

    return state


async def apply_node(state: ApplicationPipelineState) -> ApplicationPipelineState:
    if state.get("error"):
        return state

    user_id = state["user_id"]
    job_id = state["job_id"]
    resume_id = state.get("resume_id")

    applier = JobApplierAgent()
    try:
        app_result = await applier.apply_to_job(
            user_id=user_id,
            job_id=job_id,
            match_id=state.get("match_id"),
            resume_id=resume_id,
        )
        return {
            "application_result": app_result,
            "application_id": str(app_result.get("_id")) if app_result and "_id" in app_result else None,
        }
    except Exception as e:
        logger.error("Job applier node failed", error=str(e), user_id=user_id, job_id=job_id)
        return {"error": str(e)}


async def verify_node(state: ApplicationPipelineState) -> ApplicationPipelineState:
    app_id = state.get("application_id")
    if not app_id:
        return state

    verifier = ApplicationVerifierAgent()
    try:
        verified_app = await verifier.verify_application(app_id)
        return {"application_result": verified_app}
    except Exception as e:
        logger.error("Verifier node failed", error=str(e), application_id=app_id)
        return state


def build_application_graph():
    builder = StateGraph(ApplicationPipelineState)
    builder.add_node("build_resume", build_resume_node)
    builder.add_node("apply", apply_node)
    builder.add_node("verify", verify_node)

    builder.add_edge(START, "build_resume")
    builder.add_edge("build_resume", "apply")
    builder.add_edge("apply", "verify")
    builder.add_edge("verify", END)

    return builder.compile()


application_pipeline = build_application_graph()
