from datetime import datetime
from typing import Literal
from pydantic import Field
from .base import MongoBaseModel, PyObjectId, utcnow


class CompanyInfo(MongoBaseModel):
    website: str | None = None
    description: str | None = None
    size: str | None = None
    industry: str | None = None


class SalaryRange(MongoBaseModel):
    min: float | None = None
    max: float | None = None
    currency: str | None = None


class HRContact(MongoBaseModel):
    name: str | None = None
    email: str | None = None
    linkedin: str | None = None


class Job(MongoBaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    source: str
    source_url: str
    external_id: str | None = None
    title: str
    company: str
    company_info: CompanyInfo = Field(default_factory=CompanyInfo)
    description: str
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    location: str = ""
    is_remote: bool = False
    employment_type: Literal["full-time", "part-time", "contract", "internship"] = "full-time"
    salary_range: SalaryRange = Field(default_factory=SalaryRange)
    application_url: str
    hr_contact: HRContact = Field(default_factory=HRContact)
    required_skills: list[str] = Field(default_factory=list)
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool = True
    enriched: bool = False
    enriched_at: datetime | None = None
    discovered_at: datetime = Field(default_factory=utcnow)
    content_hash: str  # SHA256 of title+company+location for dedup


class JobMatch(MongoBaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    user_id: PyObjectId
    job_id: PyObjectId
    compatibility_score: int  # 0–100
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    experience_match: str = ""
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    match_reasoning: str = ""
    matched_at: datetime = Field(default_factory=utcnow)
    profile_version: str = ""
