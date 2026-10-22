from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from bson import ObjectId
from datetime import datetime, timezone
import structlog
from app.db.client import get_db
from app.security.jwt import get_current_user_id
from app.templates.manager import TEMPLATE_CATALOG, render_docx_for_profile, ensure_templates_exist

router = APIRouter(prefix="/templates", tags=["templates"])
logger = structlog.get_logger()


@router.get("")
async def list_templates():
    """Return catalog of available resume templates with styles & ATS scores."""
    ensure_templates_exist()
    return {"templates": TEMPLATE_CATALOG}


@router.post("/select")
async def select_template(request: Request):
    """Set the user's active resume template."""
    user_id = get_current_user_id(request)
    body = await request.json()
    template_id = body.get("template_id")

    valid_ids = {t["id"] for t in TEMPLATE_CATALOG}
    if template_id not in valid_ids:
        raise HTTPException(status_code=400, detail=f"Invalid template ID. Must be one of: {list(valid_ids)}")

    db = get_db()
    now = datetime.now(timezone.utc)
    await db.profiles.update_one(
        {"user_id": ObjectId(user_id)},
        {"$set": {"selected_template": template_id, "updated_at": now}},
        upsert=True,
    )
    return {"ok": True, "selected_template": template_id}


@router.get("/{template_id}/download")
async def download_template_docx(template_id: str, request: Request):
    """Download the current user's profile rendered in the requested .docx template."""
    user_id = get_current_user_id(request)
    db = get_db()
    profile = await db.profiles.find_one({"user_id": ObjectId(user_id)})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Please upload a resume first.")

    valid_ids = {t["id"] for t in TEMPLATE_CATALOG}
    if template_id not in valid_ids:
        template_id = "modern_tech"

    try:
        stream = render_docx_for_profile(template_id, profile)
    except Exception as e:
        logger.error("Failed to render docx resume", error=str(e), template_id=template_id)
        raise HTTPException(status_code=500, detail=f"Failed to generate document: {str(e)}")

    pers = profile.get("personal", {})
    name = pers.get("fullName") or pers.get("full_name") or "Candidate"
    safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
    filename = f"{safe_name}_Resume_{template_id}.docx"

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
