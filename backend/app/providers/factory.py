from app.models.settings import UserSettings, AIProvider
from app.security.vault import decrypt
from .base import BaseAIProvider
from .ollama import OllamaProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .anthropic_provider import AnthropicProvider
import structlog

logger = structlog.get_logger()

# Suggested models shown in the Settings UI
PROVIDER_MODEL_SUGGESTIONS: dict[AIProvider, list[str]] = {
    "ollama": ["qwen2.5-coder:14b", "llama3.1:8b", "llama3.2:latest", "llama3.2:3b", "qwen2.5:7b"],
    "openai": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"],
    "gemini": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"],
    "anthropic": ["claude-3-5-haiku-20241022", "claude-3-haiku-20240307", "claude-3-5-sonnet-20241022"],
}


class AIProviderFactory:
    @staticmethod
    def resolve(settings: UserSettings) -> BaseAIProvider:
        """
        Decrypt credentials from user settings and return the correct provider instance.
        API keys are decrypted in memory only — never stored or logged as plaintext.
        """
        provider = settings.ai_provider
        model = settings.ai_model

        match provider:
            case "ollama":
                base_url = (
                    decrypt(settings.ai_base_url_encrypted)
                    if settings.ai_base_url_encrypted
                    else "http://host.docker.internal:11434"
                )
                return OllamaProvider(base_url=base_url, model=model)

            case "openai":
                if not settings.ai_api_key_encrypted:
                    raise ValueError("OpenAI API key not configured")
                return OpenAIProvider(
                    api_key=decrypt(settings.ai_api_key_encrypted),
                    model=model,
                )

            case "gemini":
                if not settings.ai_api_key_encrypted:
                    raise ValueError("Gemini API key not configured")
                return GeminiProvider(
                    api_key=decrypt(settings.ai_api_key_encrypted),
                    model=model,
                )

            case "anthropic":
                if not settings.ai_api_key_encrypted:
                    raise ValueError("Anthropic API key not configured")
                return AnthropicProvider(
                    api_key=decrypt(settings.ai_api_key_encrypted),
                    model=model,
                )

            case _:
                raise ValueError(f"Unknown AI provider: {provider}")
