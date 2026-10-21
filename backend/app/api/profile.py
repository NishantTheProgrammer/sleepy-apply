from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from bson import ObjectId
from app.db.client import get_db
from app.security.jwt import get_current_user_id
from app.models.profile import Profile, ProfileQuestion
from datetime import datetime, timezone
from pydantic import BaseModel
import structlog

router = APIRouter(prefix="/profile", tags=["profile"])
logger = structlog.get_logger()


@router.get("")
async def get_profile(request: Request):
    user_id = get_current_user_id(request)
    db = get_db()
    doc = await db.profiles.find_one({"user_id": ObjectId(user_id)})
    if not doc:
        return {"profile": None}
    doc["_id"] = str(doc["_id"])
    doc["user_id"] = str(doc["user_id"])
    return {"profile": doc}


@router.patch("")
async def update_profile(request: Request):
    """Partial update of the user's profile."""
    user_id = get_current_user_id(request)
    db = get_db()
    body = await request.json()
    now = datetime.now(timezone.utc)

    # Whitelist allowed top-level keys
    allowed = {
        "personal", "summary", "skills", "experience", "education",
        "projects", "certifications", "job_preferences"
    }
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    update["updated_at"] = now
    await db.profiles.update_one(
        {"user_id": ObjectId(user_id)},
        {"$set": update, "$setOnInsert": {"user_id": ObjectId(user_id), "created_at": now}},
        upsert=True,
    )
    doc = await db.profiles.find_one({"user_id": ObjectId(user_id)})
    doc["_id"] = str(doc["_id"])
    doc["user_id"] = str(doc["user_id"])
    return {"profile": doc}


@router.post("/resume")
async def upload_resume(request: Request, file: UploadFile = File(...)):
    """Upload a resume PDF — triggers the Profile Creator Agent."""
    user_id = get_current_user_id(request)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    # Extract text from PDF
    from pypdf import PdfReader
    import io
    reader = PdfReader(io.BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from PDF")

    # Store raw text, trigger profile creation agent
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.profiles.update_one(
        {"user_id": ObjectId(user_id)},
        {
            "$set": {
                "resume_filename": file.filename,
                "resume_raw_text": text,
                "updated_at": now,
            },
            "$setOnInsert": {"user_id": ObjectId(user_id), "created_at": now},
        },
        upsert=True,
    )

    import asyncio
    from app.graphs.profile_graph import profile_pipeline
    asyncio.create_task(profile_pipeline.ainvoke({"user_id": user_id, "resume_text": text}))
    logger.info("Resume uploaded and profile pipeline triggered", user_id=user_id, filename=file.filename, chars=len(text))

    return {
        "ok": True,
        "message": "Resume uploaded. AI is analyzing your profile...",
        "filename": file.filename,
    }


@router.get("/questions")
async def get_pending_questions(request: Request):
    """Return AI-generated questions awaiting user answers."""
    user_id = get_current_user_id(request)
    db = get_db()
    doc = await db.profiles.find_one(
        {"user_id": ObjectId(user_id)},
        {"pending_questions": 1},
    )
    if not doc:
        return {"questions": []}
    questions = [q for q in doc.get("pending_questions", []) if not q.get("answered_at")]
    return {"questions": questions}


class AnswerRequest(BaseModel):
    question_id: str
    answer: str


@router.post("/answers")
async def submit_answers(request: Request, body: list[AnswerRequest]):
    """Submit user answers to AI profile questions."""
    user_id = get_current_user_id(request)
    db = get_db()
    now = datetime.now(timezone.utc)

    for item in body:
        await db.profiles.update_one(
            {
                "user_id": ObjectId(user_id),
                "pending_questions.id": item.question_id,
            },
            {
                "$set": {
                    "pending_questions.$.answer": item.answer,
                    "pending_questions.$.answered_at": now,
                    "updated_at": now,
                }
            },
        )

    # TODO: trigger profile_graph to incorporate answers
    return {"ok": True, "answered": len(body)}
