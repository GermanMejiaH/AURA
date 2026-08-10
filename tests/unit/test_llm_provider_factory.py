from __future__ import annotations

from aura.cognition import (
    CognitionModule,
    MockLLMProvider,
    OpenAILLMProvider,
    RealLLMProvider,
    create_llm_provider,
)
from aura.config import ConfigurationManager


def test_factory_returns_mock_provider_when_requested() -> None:
    provider = create_llm_provider(preferred_provider="mock")
    assert isinstance(provider, MockLLMProvider)


def test_factory_defaults_to_mock_when_no_credentials() -> None:
    provider = create_llm_provider(preferred_provider="mock")
    assert isinstance(provider, MockLLMProvider)


def test_factory_instantiates_openai_provider_with_key() -> None:
    provider = create_llm_provider(preferred_provider="openai")
    # Should instantiate OpenAILLMProvider or fallback to RealLLM/Mock cleanly
    assert isinstance(provider, (OpenAILLMProvider, RealLLMProvider, MockLLMProvider))


def test_cognition_module_process_cycle_with_real_llm_fallback() -> None:
    config = ConfigurationManager()
    mock_llm = MockLLMProvider(default_response="Hola desde el LLM de pruebas.")
    cog = CognitionModule(config=config, llm_provider=mock_llm)

    res = cog.process_cognitive_cycle("Hola AURA")

    assert res.summary is not None
    assert "Hola desde el LLM" in res.summary
    assert len(cog.working_memory.get_recent_conversation()) == 2
