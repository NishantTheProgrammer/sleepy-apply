from typing import TypeVar, Type
from pydantic import BaseModel
from .base import BaseAIProvider
import structlog

logger = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)


class OpenAIProvider(BaseAIProvider):
    provider_name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def _get_client(self):
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=self.api_key)

    async def complete(self, messages: list[dict], **kwargs) -> str:
        client = self._get_client()
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    async def structured_complete(self, messages: list[dict], schema: Type[T], **kwargs) -> T:
        client = self._get_client()
        response = await client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=schema,
            **kwargs,
        )
        return response.choices[0].message.parsed  # type: ignore

    async def health_check(self) -> bool:
        try:
            client = self._get_client()
            await client.models.list()
            return True
        except Exception:
            return False
