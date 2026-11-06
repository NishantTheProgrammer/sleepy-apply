from datetime import datetime
from typing import Any, Literal
from pydantic import Field, ConfigDict
from .base import MongoBaseModel, PyObjectId, utcnow


class LocationInfo(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    address: str = ""
    city: str = ""
    postalCode: str = ""
    country: str = ""


class PersonalInfo(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    fullName: str = ""
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: dict[str, Any] | str = Field(default_factory=dict)
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    other_links: list[str] = Field(default_factory=list)


class SubProject(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class Experience(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    company_id: str = ""
    company: str = ""
    jobTitle: str = ""
    title: str = ""
    role: str = ""
    startDate: str = ""
    start_date: str = ""
    endDate: str | None = None
    end_date: str | None = None
    current: bool = False
    is_current: bool = False
    description: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class Education(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    degree: str = ""
    institution: str = ""
    field: str = ""
    year: int | str = ""
    graduation_year: str = ""
    gpa: str | None = None
    source_type: str = "education"
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class Project(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class Achievement(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    title: str = ""
    url: str | None = None
    source: str = "original_resume"
    source_type: str = "achievement"


class JobPreferences(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    jobTitles: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    employmentTypes: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remotePreference: str | None = None
    remote_preference: str = "any"
    minimumSalary: float | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = "USD"
    industries: list[str] = Field(default_factory=list)


class ProfileQuestion(MongoBaseModel):
    id: str
    question: str
    field: str
    asked_at: datetime = Field(default_factory=utcnow)
    answered_at: datetime | None = None
    answer: str | None = None


class TailoredResumeSchema(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    job_id: str
    job_title: str
    company: str
    target_headline: str = ""
    summary: str = ""
    tailored_summary: str = ""
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    skills_breakdown: dict[str, Any] = Field(default_factory=dict)
    evidence_mappings: list[dict[str, Any]] = Field(default_factory=list)
    personal: dict[str, Any] = Field(default_factory=dict)
    skills: dict[str, list[str]] | list[str] = Field(default_factory=dict)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    achievements: list[dict[str, Any]] = Field(default_factory=list)
    template: str = "default"
    generated_at: str = ""
    validation_report: dict[str, Any] = Field(default_factory=dict)


class Profile(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    id: PyObjectId | None = Field(default=None, alias="_id")
    user_id: PyObjectId
    resume_filename: str | None = None
    resume_raw_text: str | None = None
    candidate: dict[str, Any] = Field(default_factory=dict)
    personal: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    skills: dict[str, list[str]] | list[str] = Field(default_factory=dict)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    achievements: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[dict[str, Any]] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    jobPreferences: dict[str, Any] = Field(default_factory=dict)
    job_preferences: dict[str, Any] = Field(default_factory=dict)
    additionalInformation: dict[str, Any] = Field(default_factory=dict)
    selected_template: str = "default"
    completion_score: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    pending_questions: list[ProfileQuestion] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
