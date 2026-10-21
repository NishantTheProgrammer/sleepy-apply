from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
import hashlib


class RawJobData(BaseModel):
    title: str
    company: str
    source_url: str
    description: str
    location: str = ""
    is_remote: bool = False
    employment_type: str = "full-time"
    application_url: str = ""
    external_id: str | None = None
    company_website: str | None = None
    posted_at_raw: str | None = None
    required_skills: list[str] = Field(default_factory=list)


class BaseJobSource(ABC):
    source_type: str = "base"

    @abstractmethod
    async def fetch_jobs(self, config: dict) -> list[RawJobData]:
        """Fetch raw job postings from the configured source."""
        pass

    def get_content_hash(self, job: RawJobData) -> str:
        """Generate a deterministic SHA256 hash for deduplication."""
        raw = f"{job.title.strip().lower()}|{job.company.strip().lower()}|{job.location.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()
