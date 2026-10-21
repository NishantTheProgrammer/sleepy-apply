from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId
from app.db.client import get_db
from app.security.jwt import get_current_user_id
from app.models.settings import UserSettings, UserSettingsPublic, AIProvider
from app.security.vault import encrypt
from app.providers.factory import AIProviderFactory, PROVIDER_MODEL_SUGGESTIONS
from pydantic import BaseModel
from datetime import datetime, timezone
import structlog

router = APIRouter(prefix="/settings", tags=["settings"])
logger = structlog.get_logger()


class UpdateSettingsRequest(BaseModel):
    ai_provider: AIProvider | None = None
    ai_model: str | None = None
    ai_api_key: str | None = None          # plaintext — encrypted before storing
    ai_base_url: str | None = None         # plaintext — encrypted before storing
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None       # plaintext — encrypted before storing
    notification_preferences: dict | None = None
    application_preferences: dict | None = None


@router.get("", response_model=UserSettingsPublic)
async def get_settings_route(request: Request):
    user_id = get_current_user_id(request)
    db = get_db()
    doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
    if not doc:
        # Return defaults
        return UserSettingsPublic(
            _id=ObjectId(),
            user_id=ObjectId(user_id),
            ai_provider="ollama",
            ai_model="llama3.2:1b",
            ai_api_key_set=False,
            ai_base_url_set=False,
            smtp_password_set=False,
            notification_preferences={},
            application_preferences={},
            updated_at=datetime.now(timezone.utc),
        )
    settings = UserSettings(**{**doc, "_id": doc["_id"]})
    return UserSettingsPublic.from_settings(settings)


@router.put("", response_model=UserSettingsPublic)
async def update_settings(request: Request, body: UpdateSettingsRequest):
    user_id = get_current_user_id(request)
    db = get_db()
    now = datetime.now(timezone.utc)

    update: dict = {"updated_at": now}

    if body.ai_provider is not None:
        update["ai_provider"] = body.ai_provider
    if body.ai_model is not None:
        update["ai_model"] = body.ai_model
    if body.ai_api_key is not None:
        # Encrypt before storing — plaintext never hits the database
        update["ai_api_key_encrypted"] = encrypt(body.ai_api_key)
    if body.ai_base_url is not None:
        update["ai_base_url_encrypted"] = encrypt(body.ai_base_url)
    if body.smtp_host is not None:
        update["smtp_host"] = body.smtp_host
    if body.smtp_port is not None:
        update["smtp_port"] = body.smtp_port
    if body.smtp_user is not None:
        update["smtp_user"] = body.smtp_user
    if body.smtp_password is not None:
        update["smtp_password_encrypted"] = encrypt(body.smtp_password)
    if body.notification_preferences is not None:
        update["notification_preferences"] = body.notification_preferences
    if body.application_preferences is not None:
        update["application_preferences"] = body.application_preferences

    await db.user_settings.update_one(
        {"user_id": ObjectId(user_id)},
        {"$set": update, "$setOnInsert": {"user_id": ObjectId(user_id), "created_at": now}},
        upsert=True,
    )

    doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
    settings = UserSettings(**{**doc, "_id": doc["_id"]})
    return UserSettingsPublic.from_settings(settings)


@router.post("/test-ai")
async def test_ai_provider(request: Request):
    """Test the user's configured AI provider connectivity."""
    user_id = get_current_user_id(request)
    db = get_db()
    doc = await db.user_settings.find_one({"user_id": ObjectId(user_id)})
    if not doc:
        raise HTTPException(status_code=400, detail="No AI provider configured")

    settings = UserSettings(**{**doc, "_id": doc["_id"]})
    try:
        provider = AIProviderFactory.resolve(settings)
        healthy = await provider.health_check()
        if not healthy:
            return {"ok": False, "error": "Provider unreachable"}
        # Quick smoke test
        result = await provider.complete([{"role": "user", "content": "Say 'ok' and nothing else."}])
        return {"ok": True, "response": result[:100]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/models")
async def get_model_suggestions():
    """Return model suggestions for each AI provider."""
    return PROVIDER_MODEL_SUGGESTIONS
