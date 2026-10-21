from datetime import datetime
from typing import Literal
from pydantic import Field
from .base import MongoBaseModel, PyObjectId, utcnow


class PersonalInfo(MongoBaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    other_links: list[str] = Field(default_factory=list)


class Experience(MongoBaseModel):
    company: str
    title: str
    start_date: str
    end_date: str | None = None
    is_current: bool = False
    description: str = ""
    achievements: list[str] = Field(default_factory=list)


class Education(MongoBaseModel):
    institution: str
    degree: str
    field: str
    graduation_year: str = ""
    gpa: str | None = None


class Project(MongoBaseModel):
    name: str
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None


class Certification(MongoBaseModel):
    name: str
    issuer: str
    year: str = ""
    url: str | None = None


class JobPreferences(MongoBaseModel):
    titles: list[str] = Field(default_factory=list)
    types: list[Literal["full-time", "part-time", "contract", "internship", "remote"]] = Field(
        default_factory=list
    )
    locations: list[str] = Field(default_factory=list)
    remote_preference: Literal["remote", "hybrid", "onsite", "any"] = "any"
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = "USD"
    industries: list[str] = Field(default_factory=list)
    company_sizes: list[Literal["startup", "mid", "enterprise"]] = Field(default_factory=list)
    exclude_companies: list[str] = Field(default_factory=list)


class ProfileQuestion(MongoBaseModel):
    id: str
    question: str
    field: str
    asked_at: datetime = Field(default_factory=utcnow)
    answered_at: datetime | None = None
    answer: str | None = None


class Profile(MongoBaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    user_id: PyObjectId
    resume_filename: str | None = None
    resume_raw_text: str | None = None
    personal: PersonalInfo = Field(default_factory=PersonalInfo)
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    job_preferences: JobPreferences = Field(default_factory=JobPreferences)
    completion_score: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    pending_questions: list[ProfileQuestion] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
