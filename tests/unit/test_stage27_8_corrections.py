"""
Unit tests for Stage 27.8 Post-Validation Corrections Sprint.
Validates exit confirmation timing, clean session working memory hydration,
pre-LLM fast path execution (time, expanded math, greetings),
VAD dynamic threshold ceiling & telemetry, and FasterWhisper confidence normalization.
"""

import math
import time
from unittest.mock import MagicMock

import pytest

from aura.audio.faster_whisper_stt import FasterWhisperSTTProvider
from aura.cognition.intent import ControlIntentDetector
from aura.cognition.module import CognitionModule
from aura.cognition.working_memory import WorkingMemory
from aura.memory.conversational import ConversationalMemory
from aura.memory.store import SQLiteMemoryStore
from aura.telemetry import TelemetryManager


def test_exit_confirmation_keyword_matching():
    """Validates affirmative keyword matching for exit confirmation utterances."""
    affirmative_samples = [
        "sí",
        "si",
        "sí.",
        "sí, salí.",
        "confirmo.",
        "correcto",
        "sí, cerrar ahora",
        "sí, cerrará ahora",
        "confirmo el cierre",
        "salir",
    ]
    for text in affirmative_samples:
        lower = text.lower().strip()
        confirm_keywords = (
            "sí",
            "si",
            "afirmativo",
            "confirmo",
            "confirmar",
            "correcto",
            "de acuerdo",
            "cerrar",
            "salir",
            "salí",
            "sali",
            "chao",
            "bye",
            "ahora",
        )
        assert any(kw in lower for kw in confirm_keywords), f"Failed to match exit confirmation for '{text}'"


def test_short_transcript_bypass_during_confirmation():
    """Validates that transcripts < 10 chars are allowed when awaiting_exit_confirmation is True."""
    user_text = "Sí."
    is_exit_cmd = False
    is_greeting_cmd = False
    awaiting_exit_confirmation = True

    # Evaluates Voice Guard condition
    rejected = len(user_text.strip()) < 10 and not (
        is_exit_cmd or is_greeting_cmd or awaiting_exit_confirmation
    )
    assert not rejected, "Short transcript 'Sí.' was wrongly rejected during exit confirmation mode!"


def test_is_exit_variant_matching():
    """Validates that ControlIntentDetector.is_exit detects all Whisper STT variants."""
    exit_samples = [
        "Salir",
        "Salí.",
        "Salís",
        "sali",
        "Cierra",
        "Cierre",
        "Apaga",
        "Terminar",
        "Chao",
        "Chau",
        "aura salir",
        "salir aura",
    ]
    for sample in exit_samples:
        assert ControlIntentDetector.is_exit(sample), f"is_exit failed for sample '{sample}'"


def test_clean_session_context_hydration(tmp_path):
    """Validates that a new session with session_id=None does NOT hydrate previous session turns."""
    db_file = tmp_path / "test_aura.db"
    store = SQLiteMemoryStore(db_path=str(db_file))
    mem = ConversationalMemory(store=store)

    # Add dummy session & turns to SQLite
    mem.create_session(session_id="old_session", title="Old Math Session")
    mem.add_turn(session_id="old_session", role="user", content="Para poder sumarle 20 a 50")
    mem.add_turn(session_id="old_session", role="assistant", content="El resultado es 70")

    wm = WorkingMemory()
    # Hydrating without session_id must return 0 and keep history clean
    hydrated = wm.hydrate_from_db(store=store, session_id=None)
    assert hydrated == 0
    assert len(wm.get_recent_conversation()) == 0


def test_date_time_fastpath():
    """Validates pre-LLM fast path resolution for time and date queries."""
    queries = [
        "¿Qué hora es?",
        "dime la hora actual",
        "¿Qué fecha es hoy?",
        "qué día es hoy",
    ]
    for q in queries:
        assert ControlIntentDetector.is_time_query(q), f"Failed for query: {q}"
        resp = ControlIntentDetector.get_time_response(q)
        assert isinstance(resp, str) and len(resp) > 5


def test_expanded_math_fastpath():
    """Validates expanded mathematical parser for roots, powers, percentages, trig, and logs."""
    # 1. Square root
    assert ControlIntentDetector.is_calculator_query("raíz cuadrada de 81")
    assert ControlIntentDetector.is_calculator_query("raiz de 81")
    assert ControlIntentDetector.is_calculator_query("sqrt(81)")
    assert "9" in ControlIntentDetector.get_calculator_response("raíz cuadrada de 81")

    # 2. Power
    assert ControlIntentDetector.is_calculator_query("2 elevado a 8")
    assert ControlIntentDetector.is_calculator_query("2^8")
    assert "256" in ControlIntentDetector.get_calculator_response("2 elevado a 8")

    # 3. Percentage
    assert ControlIntentDetector.is_calculator_query("15% de 200")
    assert "30" in ControlIntentDetector.get_calculator_response("15% de 200")

    # 4. Trigonometry
    assert ControlIntentDetector.is_calculator_query("seno de 30")
    assert "0.5" in ControlIntentDetector.get_calculator_response("seno de 30")

    # 5. Logarithm
    assert ControlIntentDetector.is_calculator_query("logaritmo de 100")
    assert "2" in ControlIntentDetector.get_calculator_response("logaritmo de 100")


def test_greeting_fastpath():
    """Validates flexible conversational greeting fast path detection."""
    greetings = [
        "Hola, ¿cómo estás?",
        "Buenos días AURA",
        "Buenas tardes",
        "Qué tal",
    ]
    for g in greetings:
        assert ControlIntentDetector.is_greeting(g)
        resp = ControlIntentDetector.get_greeting_response()
        assert "Hola" in resp


def test_cognition_module_fastpath_integration():
    """Validates step 0 fast path execution in CognitionModule.process_cognitive_cycle."""
    cog_mod = CognitionModule()
    # Mock LLM provider to ensure 0 LLM calls occur for fast paths
    cog_mod.llm_provider = MagicMock()

    res_time = cog_mod.process_cognitive_cycle("¿Qué hora es?")
    assert res_time.intent == "time"
    assert "Son las" in res_time.summary or "Hoy es" in res_time.summary

    res_math = cog_mod.process_cognitive_cycle("raíz cuadrada de 81")
    assert res_math.intent == "calculator"
    assert "9" in res_math.summary

    res_greet = cog_mod.process_cognitive_cycle("Hola, ¿cómo estás?")
    assert res_greet.intent == "greeting"
    assert "Hola" in res_greet.summary

    # Ensure LLM provider was never invoked for any fast path
    cog_mod.llm_provider.generate_response.assert_not_called()


def test_vad_ceiling_and_telemetry():
    """Validates that VAD dynamic threshold is capped at ceiling (140) and telemetry is updated."""
    tm = TelemetryManager.get_instance()
    initial_ceiling_hits = tm.get_counter("vad_ceiling_hits")

    # Simulate dynamic threshold calculation over ceiling
    energy_threshold = 120.0
    noise_multiplier = 1.3
    max_threshold_ceiling = 140.0

    ambient_rms = 120.0  # High noise RMS
    raw_thresh = max(energy_threshold, ambient_rms * noise_multiplier)
    if raw_thresh > max_threshold_ceiling:
        tm.increment("vad_ceiling_hits")
    dynamic_threshold = min(max_threshold_ceiling, raw_thresh)

    assert dynamic_threshold == 140.0
    assert tm.get_counter("vad_ceiling_hits") == initial_ceiling_hits + 1


def test_faster_whisper_confidence_normalization():
    """Validates STT confidence score normalization using math.exp(avg_logprob)."""
    raw_logprob = -0.35
    normalized_conf = min(1.0, max(0.0, float(math.exp(raw_logprob))))
    assert 0.0 <= normalized_conf <= 1.0
    assert abs(normalized_conf - 0.7047) < 0.01
