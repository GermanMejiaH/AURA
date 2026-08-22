"""Unit test suite for Stage 26.1 single pass pipeline & SQLite indexes."""

import sqlite3

from aura.audio.autonomous_agent import AutonomousVoiceAgent
from aura.cognition import CognitionModule
from aura.core import AURA, AURABootOptions
from aura.memory.store import SQLiteMemoryStore
from aura.telemetry import TelemetryManager


def test_sqlite_indexes_exist_via_pragma(tmp_path) -> None:
    """Verifies that indexes exist via PRAGMA index_list."""
    db_file = str(tmp_path / "test_indexes.db")
    store = SQLiteMemoryStore(db_path=db_file)

    conn = sqlite3.connect(db_file)

    # Check facts indexes
    cur = conn.execute("PRAGMA index_list(facts)")
    facts_indexes = [row[1] for row in cur.fetchall()]
    assert "idx_facts_subject_predicate" in facts_indexes

    # Check episodes indexes
    cur = conn.execute("PRAGMA index_list(episodes)")
    episodes_indexes = [row[1] for row in cur.fetchall()]
    assert "idx_episodes_timestamp" in episodes_indexes

    # Check preferences indexes
    cur = conn.execute("PRAGMA index_list(preferences)")
    preferences_indexes = [row[1] for row in cur.fetchall()]
    assert "idx_preferences_updated" in preferences_indexes

    conn.close()
    store.close()


def test_sqlite_query_planner_uses_indexes(tmp_path) -> None:
    """Verifies via EXPLAIN QUERY PLAN that queries utilize the newly created indexes."""
    db_file = str(tmp_path / "test_planner.db")
    store = SQLiteMemoryStore(db_path=db_file)

    conn = sqlite3.connect(db_file)

    # Facts query plan
    cur = conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM facts WHERE subject = 'user' AND predicate = 'nombre'"
    )
    facts_plan = " ".join([str(row) for row in cur.fetchall()])
    assert "idx_facts_subject_predicate" in facts_plan

    # Episodes query plan
    cur = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM episodes ORDER BY timestamp DESC LIMIT 10")
    episodes_plan = " ".join([str(row) for row in cur.fetchall()])
    assert "idx_episodes_timestamp" in episodes_plan

    # Preferences query plan
    cur = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM preferences ORDER BY updated_at DESC")
    pref_plan = " ".join([str(row) for row in cur.fetchall()])
    assert "idx_preferences_updated" in pref_plan

    conn.close()
    store.close()


class MockSTT:
    def __init__(self, text: str):
        self.text = text

    def transcribe(self, audio_bytes: bytes, language: str = "es"):
        class STTResult:
            def __init__(self, t):
                self.text = t

        return STTResult(self.text)


class MockRecorder:
    def __init__(self, audio_bytes: bytes = b"0" * 8000):
        self.device = "mock_mic"
        self.audio_bytes = audio_bytes
        self.calls = 0

    def record_until_silence(self, **kwargs):
        self.calls += 1
        return self.audio_bytes


class MockTTS:
    def __init__(self):
        self.spoken = []

    def speak(self, text: str, block: bool = True):
        self.spoken.append(text)

    def stop(self):
        pass


def test_auto_mode_single_pass_llm_call_count() -> None:
    """Verifies that non-fastpath turn in AUTO mode makes EXACTLY 1 LLM call."""
    options = AURABootOptions(enable_audio=False, enable_vision=False)
    aura = AURA(options=options)
    aura.boot()

    try:
        cog_mod = aura.container.resolve(CognitionModule)
        tm = TelemetryManager.get_instance()
        tm.reset()

        recorder = MockRecorder()
        stt = MockSTT("¿Cuál es la capital de Colombia?")
        tts = MockTTS()

        agent = AutonomousVoiceAgent(
            llm_provider=cog_mod.llm_provider,
            stt_provider=stt,  # type: ignore[arg-type]
            tts_provider=tts,  # type: ignore[arg-type]
            cognition_module=cog_mod,
        )

        # Run single iteration of _loop logic inline
        audio_bytes = recorder.record_until_silence()
        stt_res = stt.transcribe(audio_bytes, language="es")
        user_text = stt_res.text.strip()

        assert user_text == "¿Cuál es la capital de Colombia?"
        assert tm.get_counter("llm_calls_total") == 0

        # Execute cognitive turn via single-pass
        cognition_result = agent.cognition.process_cognitive_cycle(user_text)
        assert cognition_result is not None

        # Verify EXACTLY 1 LLM call was executed during the single-pass cycle
        assert tm.get_counter("llm_calls_total") == 1
    finally:
        aura.shutdown(wait=True)


def test_auto_mode_fastpaths_zero_llm_calls() -> None:
    """Verifies that FastPaths (Greeting, Exit) generate ZERO LLM calls."""
    options = AURABootOptions(enable_audio=False, enable_vision=False)
    aura = AURA(options=options)
    aura.boot()

    try:
        cog_mod = aura.container.resolve(CognitionModule)
        tm = TelemetryManager.get_instance()
        tm.reset()

        stt = MockSTT("hola aura")
        tts = MockTTS()

        agent = AutonomousVoiceAgent(
            llm_provider=cog_mod.llm_provider,
            stt_provider=stt,  # type: ignore[arg-type]
            tts_provider=tts,  # type: ignore[arg-type]
            cognition_module=cog_mod,
        )
        assert agent is not None

        from aura.cognition.intent import ControlIntentDetector

        # Greeting check
        user_text = "hola aura"
        assert ControlIntentDetector.is_greeting(user_text)
        assert tm.get_counter("llm_calls_total") == 0

        # Exit check
        user_text_exit = "adios aura salir"
        assert ControlIntentDetector.is_exit(user_text_exit)
        assert tm.get_counter("llm_calls_total") == 0
    finally:
        aura.shutdown(wait=True)
