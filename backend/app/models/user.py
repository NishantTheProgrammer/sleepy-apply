from datetime import datetime
from typing import Literal
from pydantic import Field
from .base import MongoBaseModel, PyObjectId, utcnow


class User(MongoBaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    discord_id: str
    discord_username: str
    discord_avatar: str | None = None
    email: str | None = None
    role: Literal["user", "admin"] = "user"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    last_login: datetime = Field(default_factory=utcnow)
    is_active: bool = True


class UserPublic(MongoBaseModel):
    """Safe-to-expose user representation (no sensitive fields)."""
    id: PyObjectId = Field(alias="_id")
    discord_id: str
    discord_username: str
    discord_avatar: str | None = None
    email: str | None = None
    role: Literal["user", "admin"]
    created_at: datetime
    last_login: datetime
    is_active: bool
