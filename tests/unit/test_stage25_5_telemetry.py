from aura.core import AURA, AURABootOptions
from aura.telemetry import TelemetryManager


def test_telemetry_counters_increment() -> None:
    """Verifies that TelemetryManager counters increment correctly."""
    tm = TelemetryManager()
    tm.reset()

    tm.increment("llm_calls_total")
    tm.increment("llm_calls_success")
    tm.increment("llm_calls_failed", 2)
    tm.increment("llm_rate_limit_429")
    tm.increment("fastpath_greetings", 5)
    tm.increment("fastpath_memory_queries", 3)
    tm.increment("memory_writes", 4)
    tm.increment("memory_retrievals", 10)
    tm.increment("speech_events_detected", 8)
    tm.increment("autonomy_cycles", 15)

    assert tm.get_counter("llm_calls_total") == 1
    assert tm.get_counter("llm_calls_success") == 1
    assert tm.get_counter("llm_calls_failed") == 2
    assert tm.get_counter("llm_rate_limit_429") == 1
    assert tm.get_counter("fastpath_greetings") == 5
    assert tm.get_counter("fastpath_memory_queries") == 3
    assert tm.get_counter("memory_writes") == 4
    assert tm.get_counter("memory_retrievals") == 10
    assert tm.get_counter("speech_events_detected") == 8
    assert tm.get_counter("autonomy_cycles") == 15


def test_telemetry_latency_aggregation() -> None:
    """Verifies latency metric aggregation (avg, min, max, count)."""
    tm = TelemetryManager()
    tm.reset()

    tm.record_latency("time_llm_ms", 1000.0)
    tm.record_latency("time_llm_ms", 2000.0)
    tm.record_latency("time_llm_ms", 3000.0)

    summary = tm.get_latency_summary("time_llm_ms")
    assert summary is not None
    assert summary.count == 3
    assert summary.min_ms == 1000.0
    assert summary.max_ms == 3000.0
    assert summary.avg_ms == 2000.0

    all_lats = tm.get_all_latencies()
    assert "time_llm_ms" in all_lats
    assert all_lats["time_llm_ms"].avg_ms == 2000.0


def test_telemetry_auto_mode_analytics() -> None:
    """Verifies interaction analytics recording for AUTO mode decisions."""
    tm = TelemetryManager()
    tm.reset()

    tm.record_interaction("hola aura", "FASTPATH_GREETING")
    tm.record_interaction("cual es mi nombre", "FASTPATH_MEMORY")
    tm.record_interaction("cual es la capital de Francia", "RESPOND")
    tm.record_interaction("ruido aleatorio", "IGNORE")

    recs = tm.get_recent_interactions()
    assert len(recs) == 4
    assert recs[0].input_text == "hola aura"
    assert recs[0].decision_type == "FASTPATH_GREETING"
    assert recs[1].decision_type == "FASTPATH_MEMORY"
    assert recs[2].decision_type == "RESPOND"
    assert recs[3].decision_type == "IGNORE"

    # Counter auto-increment check
    assert tm.get_counter("decision_fastpath_greeting_count") == 1
    assert tm.get_counter("decision_respond_count") == 1
    assert tm.get_counter("decision_ignore_count") == 1


def test_telemetry_performance_report_output() -> None:
    """Verifies that get_performance_report returns formatted text matching specification."""
    tm = TelemetryManager()
    tm.reset()

    tm.increment("llm_calls_total", 15)
    tm.increment("llm_calls_success", 14)
    tm.increment("llm_calls_failed", 1)
    tm.increment("llm_rate_limit_429", 1)

    tm.increment("fastpath_greetings", 23)
    tm.increment("fastpath_memory_queries", 9)

    tm.record_latency("time_stt_ms", 420.0)
    tm.record_latency("time_cognition_ms", 95.0)
    tm.record_latency("time_llm_ms", 1810.0)
    tm.record_latency("time_turn_ms", 2400.0)

    tm.increment("memory_writes", 12)
    tm.increment("memory_retrievals", 31)

    report = tm.get_performance_report()

    assert "AURA PERFORMANCE REPORT" in report
    assert "LLM Calls: 15" in report
    assert "Successful: 14" in report
    assert "Failed: 1" in report
    assert "429 Events: 1" in report
    assert "Greetings FastPath: 23" in report
    assert "Memory FastPath: 9" in report
    assert "Average STT:\n420 ms" in report
    assert "Average Cognition:\n95 ms" in report
    assert "Average LLM:\n1810 ms" in report
    assert "Average Turn:\n2400 ms" in report
    assert "Memory Writes:\n12" in report
    assert "Memory Reads:\n31" in report


def test_telemetry_survives_system_boot() -> None:
    """Verifies that TelemetryManager is registered in IoC container and accessible via AURA."""
    options = AURABootOptions(enable_audio=False, enable_vision=False)
    aura = AURA(options=options)
    aura.boot()
    try:
        assert aura.telemetry is not None
        assert aura.container.has(TelemetryManager)
        resolved_tm = aura.container.resolve(TelemetryManager)
        assert resolved_tm is aura.telemetry
    finally:
        aura.shutdown(wait=True)
