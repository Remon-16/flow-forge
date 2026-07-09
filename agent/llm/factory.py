"""LLM provider factory — create ChatModel instances for different providers."""

import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel

from config.settings import Settings

logger = logging.getLogger(__name__)


def create_chat_model(settings: Settings, **overrides) -> BaseChatModel:
    """Create a LangChain-compatible ChatModel from Settings.

    Args:
        settings: Global settings loaded from .env / env vars.
        **overrides: Optional per-agent overrides (e.g. temperature).

    Returns:
        A BaseChatModel instance (ChatOpenAI, etc.).

    Raises:
        ValueError: If the provider is unsupported.
    """
    provider = settings.llm_provider.lower()
    model = overrides.get("model", settings.llm_model)
    temperature = overrides.get("temperature", settings.llm_temperature)
    max_tokens = overrides.get("max_tokens", settings.llm_max_tokens)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        chat_kwargs: dict = {
            "model": model,
            "api_key": settings.llm_api_key,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "request_timeout": settings.llm_request_timeout,
        }
        if settings.llm_base_url:
            chat_kwargs["base_url"] = settings.llm_base_url

        return ChatOpenAI(**chat_kwargs)

    # Extend here: provider == "azure", "anthropic", "ollama" ...

    raise ValueError(f"Unsupported LLM provider: {provider}")
