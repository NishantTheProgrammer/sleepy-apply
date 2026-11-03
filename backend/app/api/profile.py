import os
from typing import Any
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from bson import ObjectId
from app.db.client import get_db
from app.security.jwt import get_current_user_id
from app.models.profile import Profile, ProfileQuestion
from app.models.settings import UserSettings
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

    # Auto-recovery for stalled or interrupted resume analysis (> 60s)
    if doc.get("is_analyzing"):
        started = doc.get("analysis_started_at")
        now = datetime.now(timezone.utc)
        if started:
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed = (now - started).total_seconds()
        else:
            elapsed = 999

        if elapsed > 60:
            logger.info("Auto-recovering stalled resume analysis", user_id=user_id, elapsed=elapsed)
            raw_text = doc.get("resume_raw_text") or ""
            if raw_text:
                from app.agents.profile_creator import ProfileCreatorAgent
                from app.agents.screening_agent import ScreeningQAAgent
                agent = ProfileCreatorAgent()
                parsed = agent._heuristic_parse(raw_text)
                parsed = agent._normalize_extracted_data(parsed)
                screening_agent = ScreeningQAAgent()
                suggested_roles = screening_agent.generate_suggested_roles(parsed)
                screening_qs = await screening_agent.generate_screening_questions(
                    profile=parsed,
                    target_role=suggested_roles[0] if suggested_roles else None
                )
                score = agent._calculate_completion_score(parsed)
                full_name = parsed.get("personal", {}).get("fullName")
                if full_name and full_name.lower() != "candidate":
                    await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"name": full_name}})

                update_fields = {
                    "personal": parsed.get("personal", {}),
                    "summary": parsed.get("summary", ""),
                    "skills": parsed.get("skills", {}),
                    "experience": parsed.get("experience", []),
                    "education": parsed.get("education", []),
                    "projects": parsed.get("projects", []),
                    "achievements": parsed.get("achievements", []),
                    "completion_score": score,
                    "suggested_roles": suggested_roles,
                    "screening_questions": screening_qs,
                    "is_analyzing": False,
                    "analysis_error": None,
                    "analyzed_at": now,
                    "updated_at": now,
                }
                await db.profiles.update_one({"user_id": ObjectId(user_id)}, {"$set": update_fields})
                doc.update(update_fields)
            else:
                await db.profiles.update_one(
                    {"user_id": ObjectId(user_id)},
                    {"$set": {"is_analyzing": False, "analysis_error": "Analysis timed out", "updated_at": now}}
                )
                doc["is_analyzing"] = False

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
        "projects", "certifications", "job_preferences", "jobPreferences",
        "achievements", "additionalInformation", "additional_information",
        "selected_template",
    }
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # Recalculate completion score
    from app.agents.profile_creator import ProfileCreatorAgent
    agent = ProfileCreatorAgent()
    current_doc = await db.profiles.find_one({"user_id": ObjectId(user_id)}) or {}
    merged = {**current_doc, **update}
    update["completion_score"] = agent._calculate_completion_score(merged)
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
    """Upload a resume (PDF or DOCX) — triggers the Profile Creator Agent."""
    user_id = get_current_user_id(request)

    filename_lower = (file.filename or "").lower()
    if not (filename_lower.endswith(".pdf") or filename_lower.endswith(".docx")):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are accepted")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    text = ""
    import io
    if filename_lower.endswith(".pdf"):
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(content))
            # Extract text preserving visual column layout
            pages_text = []
            for page in reader.pages:
                try:
                    p_txt = page.extract_text(extraction_mode="layout")
                except Exception:
                    p_txt = page.extract_text()
                if p_txt:
                    pages_text.append(p_txt)
            text = "\n".join(pages_text)
            if not text.strip():
                # Fallback to plain extraction
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            logger.error("Failed to extract PDF text", error=str(e), filename=file.filename)
            raise HTTPException(status_code=400, detail=f"Failed to read PDF: {str(e)}")
    elif filename_lower.endswith(".docx"):
        import docx
        try:
            doc = docx.Document(io.BytesIO(content))
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            table_cells = [cell.text for t in doc.tables for row in t.rows for cell in row.cells if cell.text.strip()]
            text = "\n".join(paras + table_cells)
        except Exception as e:
            logger.error("Failed to extract DOCX text", error=str(e), filename=file.filename)
            raise HTTPException(status_code=400, detail=f"Failed to read DOCX: {str(e)}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract any readable text from uploaded file")

    # Clean excessive whitespace while preserving section layout
    import re
    cleaned_text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # Clear old information completely across all relevant collections:
    # 1. Purge previous job matches, tailored resumes, applications, and workflow runs
    db = get_db()
    uid = ObjectId(user_id)
    now = datetime.now(timezone.utc)
    user_match_filter = {"$or": [{"user_id": uid}, {"user_id": str(user_id)}]}

    del_matches = await db.job_matches.delete_many(user_match_filter)
    del_resumes = await db.resumes.delete_many(user_match_filter)
    del_apps = await db.applications.delete_many(user_match_filter)
    del_workflows = await db.workflow_runs.delete_many(user_match_filter)

    # Clean local on-disk stored resumes for this user
    import shutil
    storage_dir = os.path.join(os.getcwd(), "storage", "resumes", str(user_id))
    if os.path.exists(storage_dir):
        try:
            shutil.rmtree(storage_dir)
        except Exception:
            pass

    logger.info(
        "Purged user collection data on resume upload",
        user_id=user_id,
        purged_job_matches=del_matches.deleted_count,
        purged_resumes=del_resumes.deleted_count,
        purged_applications=del_apps.deleted_count,
        purged_workflow_runs=del_workflows.deleted_count,
    )

    # 2. Preserve original creation timestamp if present, otherwise set now
    existing_created_at = now
    existing_profile = await db.profiles.find_one({"user_id": uid}, {"created_at": 1})
    if existing_profile and existing_profile.get("created_at"):
        existing_created_at = existing_profile["created_at"]

    # 3. Clean fresh profile state (deleting all old experiences, skills, questions, and Q/A history)
    fresh_profile = {
        "user_id": uid,
        "resume_filename": file.filename,
        "resume_raw_text": cleaned_text,
        "is_analyzing": True,
        "analysis_started_at": now,
        "analysis_error": None,
        "personal": {},
        "summary": "",
        "skills": {},
        "experience": [],
        "education": [],
        "projects": [],
        "achievements": [],
        "jobPreferences": {},
        "job_preferences": {},
        "additionalInformation": {},
        "completion_score": 0,
        "missing_fields": [],
        "pending_questions": [],
        "qa_history": [],
        "screening_questions": [],
        "target_role": None,
        "suggested_roles": [],
        "created_at": existing_created_at,
        "updated_at": now,
    }

    await db.profiles.replace_one({"user_id": uid}, fresh_profile, upsert=True)

    import asyncio
    from app.graphs.profile_graph import profile_pipeline
    asyncio.create_task(profile_pipeline.ainvoke({"user_id": user_id, "resume_text": cleaned_text}))
    logger.info("Resume uploaded and profile pipeline triggered", user_id=user_id, filename=file.filename, chars=len(cleaned_text))

    return {
        "ok": True,
        "is_analyzing": True,
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


class SelectRoleRequest(BaseModel):
    role: str


class ScreeningAnswerItem(BaseModel):
    question_id: str
    question: str | None = None
    answer: Any
    category: str | None = None
    type: str | None = None


class SubmitScreeningAnswersRequest(BaseModel):
    answers: list[ScreeningAnswerItem]
    target_role: str | None = None


@router.get("/screening")
async def get_screening_data(request: Request):
    """
    Returns suggested target profile chips, active screening questions,
    and answered Q/A history for the candidate.
    """
    user_id = get_current_user_id(request)
    db = get_db()
    profile = await db.profiles.find_one({"user_id": ObjectId(user_id)})
    has_content = bool(
        profile and (
            profile.get("resume_filename") or
            (isinstance(profile.get("experience"), list) and len(profile.get("experience", [])) > 0) or
            (isinstance(profile.get("skills"), dict) and any(profile.get("skills", {}).values()))
        )
    )
    if not profile or not has_content:
        return {
            "target_roles": [],
            "selected_role": None,
            "questions": [],
            "qa_history": [],
        }

    from app.agents.screening_agent import ScreeningQAAgent
    agent = ScreeningQAAgent()

    target_roles = profile.get("suggested_roles")
    if not target_roles or not isinstance(target_roles, list) or len(target_roles) == 0:
        target_roles = agent.generate_suggested_roles(profile)
        await db.profiles.update_one(
            {"user_id": ObjectId(user_id)},
            {"$set": {"suggested_roles": target_roles}}
        )

    # Determine selected role
    selected_role = profile.get("target_role")
    if not selected_role:
        prefs = profile.get("job_preferences") or profile.get("jobPreferences") or {}
        titles = prefs.get("jobTitles") or prefs.get("titles") or []
        selected_role = titles[0] if titles else (target_roles[0] if target_roles else None)

    questions = profile.get("screening_questions", [])
    if not questions or len(questions) == 0:
        settings_doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
        user_settings = UserSettings(**settings_doc) if settings_doc else None
        questions = await agent.generate_screening_questions(
            profile=profile,
            target_role=selected_role,
            user_settings=user_settings
        )
        await db.profiles.update_one(
            {"user_id": ObjectId(user_id)},
            {"$set": {"screening_questions": questions}}
        )

    return {
        "target_roles": target_roles,
        "selected_role": selected_role,
        "questions": questions,
        "qa_history": profile.get("qa_history", []),
    }


@router.post("/screening/select-role")
async def select_target_role(request: Request, body: SelectRoleRequest):
    """
    User picks or enters their target role.
    Generates dynamic recruiter screening questions specific to this role via fast local AI model.
    """
    user_id = get_current_user_id(request)
    db = get_db()
    now = datetime.now(timezone.utc)
    profile = await db.profiles.find_one({"user_id": ObjectId(user_id)})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Please upload a resume first.")

    chosen_role = body.role.strip()
    if not chosen_role:
        raise HTTPException(status_code=400, detail="Target role cannot be empty")

    from app.agents.screening_agent import ScreeningQAAgent
    agent = ScreeningQAAgent()

    settings_doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
    user_settings = UserSettings(**settings_doc) if settings_doc else None

    # Generate role-specific recruiter questions using fast local model
    questions = await agent.generate_screening_questions(
        profile=profile,
        target_role=chosen_role,
        user_settings=user_settings
    )

    # Update job preferences with the selected target role at the top
    current_titles = profile.get("job_preferences", {}).get("jobTitles", [])
    updated_titles = [chosen_role] + [t for t in current_titles if t.lower() != chosen_role.lower()]

    await db.profiles.update_one(
        {"user_id": ObjectId(user_id)},
        {
            "$set": {
                "target_role": chosen_role,
                "job_preferences.jobTitles": updated_titles,
                "jobPreferences.jobTitles": updated_titles,
                "screening_questions": questions,
                "updated_at": now,
            }
        }
    )

    return {
        "ok": True,
        "selected_role": chosen_role,
        "questions": questions,
    }


@router.post("/screening/answer")
async def submit_screening_answers(request: Request, body: SubmitScreeningAnswersRequest):
    """
    Submits user answers to the screening questions and stores them in Q/A history against the user.
    Also syncs relevant answers into candidate profile and re-scores active jobs.
    """
    user_id = get_current_user_id(request)
    db = get_db()
    now = datetime.now(timezone.utc)
    profile = await db.profiles.find_one({"user_id": ObjectId(user_id)})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    existing_qa = profile.get("qa_history", [])
    existing_map = {item.get("id"): item for item in existing_qa}

    for item in body.answers:
        raw_ans = item.answer
        if isinstance(raw_ans, list):
            formatted_answer = ", ".join(str(x).strip() for x in raw_ans if str(x).strip())
        else:
            formatted_answer = str(raw_ans).strip()

        qa_entry = {
            "id": item.question_id,
            "question": item.question or f"Question {item.question_id}",
            "answer": formatted_answer,
            "raw_answer": raw_ans,
            "type": item.type or ("multiselect" if isinstance(raw_ans, list) else "single_select"),
            "category": item.category or "screening",
            "target_role": body.target_role or profile.get("target_role"),
            "answered_at": now.isoformat(),
        }
        existing_map[item.question_id] = qa_entry

    updated_qa = list(existing_map.values())

    current_questions = profile.get("screening_questions", [])
    for q in current_questions:
        if q.get("id") in existing_map:
            q["answer"] = existing_map[q["id"]]["answer"]
            q["answered_at"] = existing_map[q["id"]]["answered_at"]

    update_fields: dict[str, Any] = {
        "qa_history": updated_qa,
        "screening_questions": current_questions,
        "updated_at": now,
    }

    if body.target_role:
        update_fields["target_role"] = body.target_role.strip()

    await db.profiles.update_one(
        {"user_id": ObjectId(user_id)},
        {"$set": update_fields}
    )

    # Re-match active jobs in the background to incorporate the answers and target role
    import asyncio
    from app.agents.job_matcher import JobMatcherAgent

    async def rescore_user_jobs():
        try:
            matcher = JobMatcherAgent()
            cursor = db.jobs.find({"is_active": True}).limit(40)
            async for j in cursor:
                await matcher.match_user_and_job(user_id=user_id, job_id=str(j["_id"]), use_ai_reasoning=False)
        except Exception as e:
            logger.warning("Background job re-matching after screening answer failed", error=str(e))

    asyncio.create_task(rescore_user_jobs())

    return {
        "ok": True,
        "saved_count": len(body.answers),
        "total_qa": len(updated_qa),
        "qa_history": updated_qa,
    }


@router.post("/screening/regenerate")
async def regenerate_screening_questions(request: Request, body: SelectRoleRequest | None = None):
    """Forces AI to generate fresh recruiter screening questions for the candidate."""
    user_id = get_current_user_id(request)
    db = get_db()
    profile = await db.profiles.find_one({"user_id": ObjectId(user_id)})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    chosen_role = (body.role if body else None) or profile.get("target_role")
    from app.agents.screening_agent import ScreeningQAAgent
    agent = ScreeningQAAgent()

    settings_doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
    user_settings = UserSettings(**settings_doc) if settings_doc else None

    questions = await agent.generate_screening_questions(
        profile=profile,
        target_role=chosen_role,
        user_settings=user_settings
    )

    await db.profiles.update_one(
        {"user_id": ObjectId(user_id)},
        {"$set": {"screening_questions": questions, "updated_at": datetime.now(timezone.utc)}}
    )

    return {"ok": True, "questions": questions}


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
