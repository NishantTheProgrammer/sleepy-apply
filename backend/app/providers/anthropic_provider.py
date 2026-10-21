import json
from typing import TypeVar, Type
from pydantic import BaseModel
from .base import BaseAIProvider
import structlog

logger = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)


class AnthropicProvider(BaseAIProvider):
    provider_name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022"):
        self.api_key = api_key
        self.model = model

    def _get_client(self):
        import anthropic
        return anthropic.AsyncAnthropic(api_key=self.api_key)

    def _split_system(self, messages: list[dict]) -> tuple[str, list[dict]]:
        system = ""
        filtered = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                filtered.append(msg)
        return system, filtered

    async def complete(self, messages: list[dict], **kwargs) -> str:
        client = self._get_client()
        system, chat_messages = self._split_system(messages)
        response = await client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system or anthropic.NOT_GIVEN,  # type: ignore
            messages=chat_messages,
            **kwargs,
        )
        return response.content[0].text

    async def structured_complete(self, messages: list[dict], schema: Type[T], **kwargs) -> T:
        schema_json = json.dumps(schema.model_json_schema())
        system, chat_messages = self._split_system(messages)
        full_system = (system + "\n" if system else "") + (
            f"Respond ONLY with valid JSON matching this schema:\n{schema_json}\n"
            "No markdown, no explanation, just the JSON object."
        )
        raw = await self.complete(
            [{"role": "system", "content": full_system}] + chat_messages, **kwargs
        )
        return schema.model_validate_json(raw)

    async def health_check(self) -> bool:
        try:
            client = self._get_client()
            await client.models.list()
            return True
        except Exception:
            return False
