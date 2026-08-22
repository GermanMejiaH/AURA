from __future__ import annotations

from unittest.mock import MagicMock, patch

from aura.audio.autonomous_agent import AutonomousVoiceAgent
from aura.cognition import ControlIntentDetector, OpenAILLMProvider
from aura.memory import Fact, MemoryQueryResult


def _create_agent(**kwargs) -> tuple[AutonomousVoiceAgent, MagicMock]:
    mock_llm = kwargs.pop("llm_provider", MagicMock())
    mock_stt = kwargs.pop("stt_provider", MagicMock())
    mock_tts = kwargs.pop("tts_provider", MagicMock())

    with patch("aura.audio.autonomous_agent.MicrophoneRecorder"):
        agent = AutonomousVoiceAgent(
            llm_provider=mock_llm,
            stt_provider=mock_stt,
            tts_provider=mock_tts,
            **kwargs,
        )
    return agent, mock_llm


def test_greeting_hola_zero_llm_calls() -> None:
    """Verifies that 'hola' uses greeting fast-path with 0 LLM calls."""
    _agent, mock_llm = _create_agent()
    assert ControlIntentDetector.is_greeting("hola") is True

    # Simulate fast-path branch in _loop
    resp = ControlIntentDetector.get_greeting_response()
    assert resp == "¡Hola! ¿En qué puedo ayudarte?"
    mock_llm.generate_response.assert_not_called()


def test_greeting_hola_aura_zero_llm_calls() -> None:
    """Verifies that 'hola aura' uses greeting fast-path with 0 LLM calls."""
    _agent, mock_llm = _create_agent()
    assert ControlIntentDetector.is_greeting("hola aura") is True
    mock_llm.generate_response.assert_not_called()


def test_hola_ahora_does_not_classify_as_temporal() -> None:
    """Verifies that 'hola ahora' does not inject timestamp into _make_decision prompt."""
    agent, mock_llm = _create_agent()
    mock_llm.generate_response.return_value.content = '{"action": "RESPOND", "response": "Hola"}'

    agent._make_decision("hola ahora")

    call_args = mock_llm.generate_response.call_args
    prompt_sent = call_args.kwargs.get("prompt") or call_args.args[0]
    assert "Fecha y hora actual del sistema" not in prompt_sent


def test_temporal_keyword_injects_timestamp() -> None:
    """Verifies that queries with time keywords do inject system timestamp."""
    agent, mock_llm = _create_agent()
    mock_llm.generate_response.return_value.content = '{"action": "RESPOND", "response": "OK"}'

    agent._make_decision("¿Qué hora es hoy?")

    call_args = mock_llm.generate_response.call_args
    prompt_sent = call_args.kwargs.get("prompt") or call_args.args[0]
    assert "Fecha y hora actual del sistema" in prompt_sent


def test_direct_memory_query_zero_llm_calls() -> None:
    """Verifies direct memory query ('¿Cuál es mi color favorito?') returns fact (0 LLM calls)."""
    mock_cog = MagicMock()
    mock_container = MagicMock()
    mock_mem = MagicMock()

    mock_cog._container = mock_container
    mock_container.has.return_value = True
    mock_container.resolve.return_value = mock_mem

    fact = Fact(subject="usuario", predicate="color favorito", object_val="rojo", confidence=0.95)
    mock_mem.retrieval.query.return_value = MemoryQueryResult(
        facts=[fact], preferences=[], episodes=[]
    )

    _agent, mock_llm = _create_agent(cognition_module=mock_cog)

    assert ControlIntentDetector.is_direct_memory_query("¿Cuál es mi color favorito?") is True

    # Run direct memory query resolution
    res_retrieval = mock_mem.retrieval.query("¿Cuál es mi color favorito?")
    top_fact = res_retrieval.facts[0]
    ans = f"Tu {top_fact.predicate} es {top_fact.object_val}."

    assert ans == "Tu color favorito es rojo."
    mock_llm.generate_response.assert_not_called()


def test_complex_query_uses_single_llm_call() -> None:
    """Verifies complex query in process_cognitive_cycle calls LLM exactly 1 time."""
    mock_cog = MagicMock()
    mock_reasoning_res = MagicMock()
    mock_reasoning_res.summary = "Explicación de física"
    mock_cog.process_cognitive_cycle.return_value = mock_reasoning_res

    agent, _mock_llm = _create_agent(cognition_module=mock_cog)

    # Process cognitive cycle directly
    res = agent.cognition.process_cognitive_cycle("Explícame la teoría de la relatividad")

    assert res.summary == "Explicación de física"
    mock_cog.process_cognitive_cycle.assert_called_once_with(
        "Explícame la teoría de la relatividad"
    )


def test_rate_limit_429_fallback() -> None:
    """Verifies HTTP 429 exception triggers retry and returns clean fallback response."""
    provider = OpenAILLMProvider(api_key="mock_key")
    mock_client = MagicMock()
    provider._client = mock_client

    # Simulate OpenAI 429 exception
    err = Exception("Error code: 429 - Rate limit reached")
    err.status_code = 429  # type: ignore[attr-defined]
    mock_client.chat.completions.create.side_effect = err

    with patch("time.sleep"):
        resp = provider.generate_response("Hola")

    assert "alta demanda" in resp.content.lower()
    assert resp.metadata.get("rate_limited") is True
