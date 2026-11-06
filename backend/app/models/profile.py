from datetime import datetime
from typing import Any, Literal
from pydantic import Field, ConfigDict, model_validator
from .base import MongoBaseModel, PyObjectId, utcnow


class CanonicalDict(dict):
    """Dictionary supporting transparent backward-compatibility for legacy field aliases
    while serializing and storing ONLY canonical fields with zero duplication.
    """
    _ALIASES = {
        "fullName": "full_name",
        "jobTitle": "title",
        "role": "title",
        "startDate": "start_date",
        "endDate": "end_date",
        "current": "is_current",
        "highlights": "responsibilities",
        "tech_stack": "technologies",
        "graduation_year": "year",
        "jobTitles": "titles",
        "employmentTypes": "types",
        "remotePreference": "remote_preference",
        "minimumSalary": "salary_min",
        "jobPreferences": "job_preferences",
    }

    def __getitem__(self, key: Any) -> Any:
        if key not in self and isinstance(key, str):
            if key == "title" and "name" in self:
                return super().__getitem__("name")
            if key in self._ALIASES and self._ALIASES[key] in self:
                return super().__getitem__(self._ALIASES[key])
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self and isinstance(key, str):
            if key == "title" and "name" in self:
                return super().get("name", default)
            if key in self._ALIASES and self._ALIASES[key] in self:
                return super().get(self._ALIASES[key], default)
        return super().get(key, default)


class LocationInfo(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    address: str = ""
    city: str = ""
    postalCode: str = ""
    country: str = ""


class PersonalInfo(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: dict[str, Any] | str = Field(default_factory=dict)
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    other_links: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_personal(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "fullName" in d and not d.get("full_name"):
                d["full_name"] = d["fullName"]
            return d
        return data

    @property
    def fullName(self) -> str:
        return self.full_name


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
    title: str = ""
    start_date: str = ""
    end_date: str | None = None
    is_current: bool = False
    description: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_experience(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if not d.get("title"):
                d["title"] = d.get("jobTitle") or d.get("role") or ""
            if not d.get("start_date"):
                d["start_date"] = d.get("startDate") or ""
            if not d.get("end_date") and "endDate" in d:
                d["end_date"] = d["endDate"]
            if "current" in d and "is_current" not in d:
                d["is_current"] = bool(d["current"])
            if not d.get("responsibilities") and "highlights" in d:
                d["responsibilities"] = d["highlights"]
            return d
        return data

    @property
    def jobTitle(self) -> str:
        return self.title

    @property
    def role(self) -> str:
        return self.title

    @property
    def startDate(self) -> str:
        return self.start_date

    @property
    def endDate(self) -> str | None:
        return self.end_date

    @property
    def current(self) -> bool:
        return self.is_current

    @property
    def highlights(self) -> list[str]:
        return self.responsibilities


class Education(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    degree: str = ""
    institution: str = ""
    field: str = ""
    year: int | str = ""
    gpa: str | None = None
    source_type: str = "education"
    evidence: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_education(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if not d.get("year") and "graduation_year" in d:
                d["year"] = d["graduation_year"]
            return d
        return data

    @property
    def graduation_year(self) -> str:
        return str(self.year)


class Project(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_project(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if not d.get("technologies") and "tech_stack" in d:
                d["technologies"] = d["tech_stack"]
            if not d.get("name") and "title" in d:
                d["name"] = d["title"]
            return d
        return data

    @property
    def title(self) -> str:
        return self.name

    @property
    def tech_stack(self) -> list[str]:
        return self.technologies


class Achievement(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    title: str = ""
    url: str | None = None
    source: str = "original_resume"
    source_type: str = "achievement"


class JobPreferences(MongoBaseModel):
    model_config = ConfigDict(extra="allow")
    titles: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_preference: str = "any"
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = "USD"
    industries: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_job_preferences(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if not d.get("titles") and "jobTitles" in d:
                d["titles"] = d["jobTitles"]
            if not d.get("types") and "employmentTypes" in d:
                d["types"] = d["employmentTypes"]
            if "remotePreference" in d and "remote_preference" not in d:
                d["remote_preference"] = d["remotePreference"]
            if "minimumSalary" in d and "salary_min" not in d:
                d["salary_min"] = d["minimumSalary"]
            return d
        return data

    @property
    def jobTitles(self) -> list[str]:
        return self.titles

    @property
    def employmentTypes(self) -> list[str]:
        return self.types

    @property
    def remotePreference(self) -> str:
        return self.remote_preference

    @property
    def minimumSalary(self) -> float | None:
        return self.salary_min


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
    job_preferences: dict[str, Any] = Field(default_factory=dict)
    additionalInformation: dict[str, Any] = Field(default_factory=dict)
    selected_template: str = "default"
    completion_score: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    pending_questions: list[ProfileQuestion] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="before")
    @classmethod
    def _normalize_profile(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if not d.get("job_preferences") and "jobPreferences" in d:
                d["job_preferences"] = d["jobPreferences"]
            return d
        return data

    @property
    def jobPreferences(self) -> dict[str, Any]:
        return self.job_preferences
