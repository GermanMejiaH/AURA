from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ..logging import get_logger
from .gemini_provider import GeminiLLMProvider
from .openai_provider import OpenAILLMProvider
from .provider import LLMProvider, MockLLMProvider
from .real_llm_provider import RealLLMProvider

if TYPE_CHECKING:
    from ..config import ConfigurationManager
    from ..container import DependencyContainer


def create_llm_provider(
    config: ConfigurationManager | None = None,
    container: DependencyContainer | None = None,
    preferred_provider: str | None = None,
) -> LLMProvider:
    """Factory function to build an interchangeable LLMProvider instance based on configuration."""
    logger = get_logger("LLMProviderFactory")

    if config is not None:
        config.load_from_env()

    prov_type = (
        preferred_provider
        or os.environ.get("AURA_LLM_PROVIDER")
        or (config.get_typed("llm.provider", str, "auto") if config else "auto")
    ).lower()

    if prov_type == "mock":
        logger.info("Initializing MockLLMProvider")
        return MockLLMProvider()

    groq_key = os.environ.get("GROQ_API_KEY") or (
        config.get_typed("llm.groq_api_key", str, "") if config else ""
    )
    openai_key = os.environ.get("OPENAI_API_KEY") or (
        config.get_typed("llm.openai_api_key", str, "") if config else ""
    )
    openrouter_key = os.environ.get("OPENROUTER_API_KEY") or (
        config.get_typed("llm.openrouter_api_key", str, "") if config else ""
    )
    gemini_key = os.environ.get("GEMINI_API_KEY") or (
        config.get_typed("llm.gemini_api_key", str, "") if config else ""
    )

    # 1. Groq Cloud (ultra fast reasoning)
    if prov_type in ("groq", "auto") and groq_key:
        try:
            logger.info("Initializing OpenAILLMProvider for Groq Cloud")
            return OpenAILLMProvider(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
                model_name=os.environ.get("AURA_LLM_MODEL", "llama-3.3-70b-versatile"),
            )
        except Exception as exc:
            logger.warning(f"Failed to initialize Groq provider: {exc}")

    # 2. OpenRouter
    if prov_type in ("openrouter", "auto") and openrouter_key:
        try:
            logger.info("Initializing OpenAILLMProvider for OpenRouter")
            default_openrouter_model = "meta-llama/llama-3.1-8b-instruct:free"
            return OpenAILLMProvider(
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                model_name=os.environ.get("AURA_LLM_MODEL", default_openrouter_model),
            )
        except Exception as exc:
            logger.warning(f"Failed to initialize OpenRouter provider: {exc}")

    # 3. OpenAI
    if prov_type in ("openai", "auto") and openai_key:
        try:
            logger.info("Initializing OpenAILLMProvider for OpenAI")
            return OpenAILLMProvider(
                api_key=openai_key,
                model_name=os.environ.get("AURA_LLM_MODEL", "gpt-4o-mini"),
            )
        except Exception as exc:
            logger.warning(f"Failed to initialize OpenAI provider: {exc}")

    # 4. Gemini
    if prov_type in ("gemini", "auto") and gemini_key and not gemini_key.startswith("AQ."):
        try:
            logger.info("Initializing GeminiLLMProvider")
            return GeminiLLMProvider(
                api_key=gemini_key,
                model_name=os.environ.get("AURA_LLM_MODEL", "gemini-2.5-flash"),
            )
        except Exception as exc:
            logger.warning(f"Failed to initialize Gemini provider: {exc}")

    # 5. Local Ollama REST API
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/api/chat")
    if prov_type == "ollama" or (prov_type == "auto" and os.environ.get("OLLAMA_BASE_URL")):
        try:
            logger.info(f"Initializing RealLLMProvider for local Ollama ({ollama_url})")
            return RealLLMProvider(
                endpoint_url=ollama_url,
                model_name=os.environ.get("AURA_LLM_MODEL", "llama3"),
            )
        except Exception as exc:
            logger.warning(f"Failed to initialize Ollama provider: {exc}")

    # Fallback to MockLLMProvider if no valid credentials/endpoints found
    logger.info("No active cloud/local LLM credentials detected. Defaulting to MockLLMProvider.")
    return MockLLMProvider()
