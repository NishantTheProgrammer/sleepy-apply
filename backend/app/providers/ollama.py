import json
from typing import TypeVar, Type
import httpx
from pydantic import BaseModel
from .base import BaseAIProvider
import structlog

logger = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)


class OllamaProvider(BaseAIProvider):
    provider_name = "ollama"

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _candidate_urls(self) -> list[str]:
        candidates = [self.base_url]
        if "localhost" in self.base_url:
            candidates.append(self.base_url.replace("localhost", "host.docker.internal"))
        elif "127.0.0.1" in self.base_url:
            candidates.append(self.base_url.replace("127.0.0.1", "host.docker.internal"))
        elif "host.docker.internal" in self.base_url:
            candidates.append(self.base_url.replace("host.docker.internal", "localhost"))
        return candidates

    async def complete(self, messages: list[dict], **kwargs) -> str:
        candidates = self._candidate_urls()
        last_err: Exception | None = None
        for base in candidates:
            try:
                async with httpx.AsyncClient(timeout=180) as client:
                    response = await client.post(
                        f"{base}/api/chat",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            **kwargs,
                        },
                    )
                    response.raise_for_status()
                    self.base_url = base
                    return response.json()["message"]["content"]
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                last_err = e
                logger.info("Ollama endpoint not reachable, trying candidate", failed_url=base, error=str(e))
                continue
            except Exception:
                raise

        if last_err:
            raise last_err
        raise RuntimeError("No reachable Ollama endpoint found")

    async def structured_complete(self, messages: list[dict], schema: Type[T], **kwargs) -> T:
        schema_json = json.dumps(schema.model_json_schema())
        system_msg = {
            "role": "system",
            "content": (
                f"You MUST respond with valid JSON that matches this schema exactly:\n{schema_json}\n"
                "Return ONLY the JSON object, no markdown, no explanation."
            ),
        }
        full_messages = [system_msg] + messages
        raw = await self.complete(full_messages, format="json", **kwargs)
        return schema.model_validate_json(raw)

    async def health_check(self) -> bool:
        for base in self._candidate_urls():
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    r = await client.get(f"{base}/api/tags")
                    if r.status_code == 200:
                        self.base_url = base
                        return True
            except Exception:
                continue
        return False
