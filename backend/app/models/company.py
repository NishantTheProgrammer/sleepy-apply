from datetime import datetime
from typing import Literal
from pydantic import Field
from .base import MongoBaseModel, PyObjectId, utcnow

CompanyGrade = Literal["Tier-1", "Tier-2", "Tier-3", "Startup"]
ATSType = Literal["greenhouse", "lever", "ashby", "workday", "custom"]


class Company(MongoBaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    name: str
    grade: CompanyGrade | str = "Tier-1"
    career_page: str
    ats_type: ATSType | str = "custom"
    board_token: str | None = None
    api_url: str | None = None
    industry: str | None = None
    location_hq: str | None = None
    is_active: bool = True
    total_jobs_fetched: int = 0
    last_fetched_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
