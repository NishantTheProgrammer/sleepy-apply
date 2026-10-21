from abc import ABC, abstractmethod
from typing import Literal
from pydantic import BaseModel, Field


class ApplicationResult(BaseModel):
    success: bool
    status: Literal["APPLIED", "REQUIRES_USER_ACTION", "FAILED"]
    action_type: Literal["captcha", "mfa", "manual_form", "missing_info"] | None = None
    message: str = ""
    details: dict = Field(default_factory=dict)


class BaseJobApplier(ABC):
    applier_name: str = "base"

    @abstractmethod
    async def apply(
        self,
        job: dict,
        user: dict,
        resume: dict,
        profile: dict,
    ) -> ApplicationResult:
        """Execute job application submission."""
        pass
