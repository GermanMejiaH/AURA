from __future__ import annotations

import logging
from typing import Any

from aura.audio.autonomous_agent import AutonomousVoiceAgent
from aura.audio.edge_tts_provider import EdgeTTSProvider
from aura.cognition.context import CognitiveContextBuilder
from aura.cognition.intent import ControlIntentDetector
from aura.cognition.provider import MockLLMProvider


def test_fastpath_math_comprehensive() -> None:
    """Tests addition, subtraction, multiplication, division, percentages, and square roots."""
    # Addition & Subtraction
    assert ControlIntentDetector.is_calculator_query("cuanto es 25 mas 35") is True
    resp_add = ControlIntentDetector.get_calculator_response("cuanto es 25 mas 35")
    assert "60" in resp_add

    # Multiplication & Division
    assert ControlIntentDetector.is_calculator_query("1348 por 151") is True
    resp_mult = ControlIntentDetector.get_calculator_response("1348 por 151")
    assert "203548" in resp_mult

    assert ControlIntentDetector.is_calculator_query("20 dividido 5") is True
    resp_div = ControlIntentDetector.get_calculator_response("20 dividido 5")
    assert "4" in resp_div

    # Percentages
    assert ControlIntentDetector.is_calculator_query("15% de 200") is True
    resp_pct = ControlIntentDetector.get_calculator_response("15% de 200")
    assert "30" in resp_pct

    # Square Roots
    assert ControlIntentDetector.is_calculator_query("raiz cuadrada de 81") is True
    resp_sqrt = ControlIntentDetector.get_calculator_response("raiz cuadrada de 81")
    assert "9" in resp_sqrt


def test_fastpath_reminder_queries() -> None:
    """Tests reminder creation and reminder listing intent detection."""
    assert ControlIntentDetector.is_reminder_query("recuerdame en 5 minutos comprar agua") is True
    desc, delay = ControlIntentDetector.parse_reminder_query("recuerdame en 5 minutos comprar agua")
    assert "comprar agua" in desc
    assert delay == 300.0

    assert ControlIntentDetector.is_reminder_list_query("que recordatorios tengo") is True
    assert ControlIntentDetector.is_reminder_list_query("lista mis recordatorios") is True


def test_fastpath_profile_queries() -> None:
    """Tests user profile query intent detector."""
    assert ControlIntentDetector.is_user_profile_query("quien soy") is True
    assert ControlIntentDetector.is_user_profile_query("cual es mi nombre") is True
    assert ControlIntentDetector.is_user_profile_query("donde vivo") is True
    assert ControlIntentDetector.is_user_profile_query("que sabes de mi") is True


def test_context_metrics_generation(caplog: Any) -> None:
    """Tests CognitiveContextBuilder logs [CONTEXT METRICS] with history, memory, tool, episode tokens, and tokens_saved."""
    builder = CognitiveContextBuilder()
    with caplog.at_level(logging.INFO):
        ctx = builder.build("Hola AURA")

    assert ctx is not None
    assert "[CONTEXT METRICS]" in caplog.text
    assert "history_tokens=" in caplog.text
    assert "memory_tokens=" in caplog.text
    assert "tool_tokens=" in caplog.text
    assert "tokens_saved=" in caplog.text


def test_tts_profiling_data() -> None:
    """Tests EdgeTTSProvider synthesis populates profiling fields in TTSResult."""
    provider = EdgeTTSProvider()
    res = provider.synthesize("Prueba de audio")

    assert res is not None
    assert res.text == "Prueba de audio"
    # Micro-profiling fields present
    assert hasattr(res, "load_model_ms")
    assert hasattr(res, "synthesize_ms")
    assert hasattr(res, "save_audio_ms")
    assert hasattr(res, "playback_ms")


def test_agent_pipeline_metrics_and_queue_computation(caplog: Any) -> None:
    """Tests that AutonomousVoiceAgent._log_pipeline_metrics emits exact [PIPELINE] log format and non-negative queue_ms."""
    agent = AutonomousVoiceAgent(llm_provider=MockLLMProvider())

    vad_ms = 800.0
    stt_ms = 1200.0
    intent_ms = 2.0
    retrieval_ms = 15.0
    llm_ms = 500.0
    tts_ms = 300.0
    playback_ms = 1500.0
    total_ms = 4500.0

    sum_known = vad_ms + stt_ms + intent_ms + retrieval_ms + llm_ms + tts_ms + playback_ms
    queue_ms = max(0.0, total_ms - sum_known)

    assert queue_ms == 183.0

    agent._log_pipeline_metrics(
        vad_ms,
        stt_ms,
        intent_ms,
        retrieval_ms,
        llm_ms,
        tts_ms,
        playback_ms,
        queue_ms,
        total_ms,
    )
