from abc import ABC, abstractmethod
from typing import TypeVar, Type
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseAIProvider(ABC):
    """Abstract base for all AI providers."""

    provider_name: str

    @abstractmethod
    async def complete(self, messages: list[dict], **kwargs) -> str:
        """Generate a text completion from a list of chat messages."""
        ...

    @abstractmethod
    async def structured_complete(self, messages: list[dict], schema: Type[T], **kwargs) -> T:
        """Generate a structured completion that validates against a Pydantic schema."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider is reachable and configured correctly."""
        ...
