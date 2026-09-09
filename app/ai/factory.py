from app.ai.interface import AIProvider
from app.ai.providers.http_providers import (
    AnthropicProvider,
    GeminiProvider,
    OpenAICompatibleProvider,
)
from app.ai.providers.mock import MockProvider
from app.core.config import Settings


def get_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "mock":
        return MockProvider()
    if not settings.ai_api_key:
        raise RuntimeError(f"AI_API_KEY is required when AI_PROVIDER={settings.ai_provider}")
    if settings.ai_provider == "gemini":
        return GeminiProvider(settings.ai_api_key, settings.ai_model, settings.ai_timeout_seconds)
    if settings.ai_provider == "anthropic":
        return AnthropicProvider(settings.ai_api_key, settings.ai_model, settings.ai_timeout_seconds)
    base_url = settings.ai_base_url or "https://api.openai.com/v1"
    return OpenAICompatibleProvider(
        settings.ai_api_key, settings.ai_model, base_url, settings.ai_timeout_seconds
    )

