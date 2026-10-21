from datetime import datetime
from typing import Literal
from pydantic import Field
from .base import MongoBaseModel, PyObjectId, utcnow


ApplicationStatus = Literal[
    "DISCOVERED",
    "MATCHED",
    "RESUME_GENERATED",
    "READY_TO_APPLY",
    "APPLYING",
    "APPLIED",
    "VERIFIED_SUCCESS",
    "VERIFIED_FAILED",
    "FAILED",
    "REQUIRES_USER_ACTION",
]


class StatusHistoryEntry(MongoBaseModel):
    status: ApplicationStatus
    timestamp: datetime = Field(default_factory=utcnow)
    reason: str | None = None


class RequiresActionInfo(MongoBaseModel):
    type: Literal["captcha", "mfa", "manual_form", "missing_info"]
    description: str
    created_at: datetime = Field(default_factory=utcnow)


class Application(MongoBaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    user_id: PyObjectId
    job_id: PyObjectId
    match_id: PyObjectId | None = None
    resume_id: PyObjectId | None = None
    status: ApplicationStatus = "DISCOVERED"
    status_history: list[StatusHistoryEntry] = Field(default_factory=list)
    applied_at: datetime | None = None
    verified_at: datetime | None = None
    failure_reason: str | None = None
    failure_details: dict | None = None
    requires_action: RequiresActionInfo | None = None
    application_method: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
