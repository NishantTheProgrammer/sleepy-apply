import json
from typing import TypeVar, Type
from pydantic import BaseModel
from .base import BaseAIProvider
import structlog

logger = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)


class GeminiProvider(BaseAIProvider):
    provider_name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model

    def _get_client(self):
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        return genai.GenerativeModel(self.model)

    def _to_gemini_messages(self, messages: list[dict]) -> tuple[str, list]:
        """Convert OpenAI-style messages to Gemini history + final prompt."""
        system = ""
        history = []
        for msg in messages[:-1]:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system = content
            elif role == "user":
                history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                history.append({"role": "model", "parts": [content]})
        last = messages[-1]["content"] if messages else ""
        return system, history, last  # type: ignore

    async def complete(self, messages: list[dict], **kwargs) -> str:
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        system, history, last_prompt = self._to_gemini_messages(messages)
        model = genai.GenerativeModel(self.model, system_instruction=system or None)
        chat = model.start_chat(history=history)
        response = await chat.send_message_async(last_prompt)
        return response.text

    async def structured_complete(self, messages: list[dict], schema: Type[T], **kwargs) -> T:
        import google.generativeai as genai
        import google.generativeai.types as gtypes
        genai.configure(api_key=self.api_key)
        schema_json = json.dumps(schema.model_json_schema())
        system, history, last_prompt = self._to_gemini_messages(messages)
        full_system = (system + "\n" if system else "") + (
            f"Respond ONLY with valid JSON matching this schema:\n{schema_json}"
        )
        model = genai.GenerativeModel(
            self.model,
            system_instruction=full_system,
            generation_config=gtypes.GenerationConfig(
                response_mime_type="application/json"
            ),
        )
        chat = model.start_chat(history=history)
        response = await chat.send_message_async(last_prompt)
        return schema.model_validate_json(response.text)

    async def health_check(self) -> bool:
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            list(genai.list_models())
            return True
        except Exception:
            return False
