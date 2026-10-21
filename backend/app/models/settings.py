from datetime import datetime
from typing import Literal
from pydantic import Field
from .base import MongoBaseModel, PyObjectId, utcnow


class NotificationPreferences(MongoBaseModel):
    discord_dm: bool = True
    email: bool = False
    events: list[str] = Field(
        default_factory=lambda: [
            "application_submitted",
            "application_failed",
            "new_jobs",
            "requires_action",
        ]
    )


class ApplicationPreferences(MongoBaseModel):
    auto_apply: bool = False
    require_confirmation: bool = True
    daily_apply_limit: int = 5
    min_compatibility_score: int = 70


AIProvider = Literal["ollama", "openai", "gemini", "anthropic"]


class UserSettings(MongoBaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    user_id: PyObjectId

    # AI provider (all encrypted except provider name and model)
    ai_provider: AIProvider = "ollama"
    ai_model: str = "llama3.2:latest"
    ai_api_key_encrypted: str | None = None      # For OpenAI/Gemini/Anthropic
    ai_base_url_encrypted: str | None = None     # For Ollama (e.g. http://localhost:11434)

    # SMTP (optional, for email notifications)
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password_encrypted: str | None = None

    # Preferences
    notification_preferences: NotificationPreferences = Field(
        default_factory=NotificationPreferences
    )
    application_preferences: ApplicationPreferences = Field(
        default_factory=ApplicationPreferences
    )

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class UserSettingsPublic(MongoBaseModel):
    """Safe projection — never exposes encrypted fields."""
    id: PyObjectId = Field(alias="_id")
    user_id: PyObjectId
    ai_provider: AIProvider
    ai_model: str
    ai_api_key_set: bool = False      # True if key is configured, never return actual key
    ai_base_url_set: bool = False
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password_set: bool = False
    notification_preferences: NotificationPreferences
    application_preferences: ApplicationPreferences
    updated_at: datetime

    @classmethod
    def from_settings(cls, s: UserSettings) -> "UserSettingsPublic":
        return cls(
            **{
                "_id": s.id,
                "user_id": s.user_id,
                "ai_provider": s.ai_provider,
                "ai_model": s.ai_model,
                "ai_api_key_set": bool(s.ai_api_key_encrypted),
                "ai_base_url_set": bool(s.ai_base_url_encrypted),
                "smtp_host": s.smtp_host,
                "smtp_port": s.smtp_port,
                "smtp_user": s.smtp_user,
                "smtp_password_set": bool(s.smtp_password_encrypted),
                "notification_preferences": s.notification_preferences,
                "application_preferences": s.application_preferences,
                "updated_at": s.updated_at,
            }
        )
