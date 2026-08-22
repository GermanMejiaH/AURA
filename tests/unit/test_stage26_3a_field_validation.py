"""Unit test suite for Stage 26.3A Field Validation & Telemetry Baseline."""

import json
import sqlite3
import threading

from aura.cli import _handle_benchmark
from aura.cognition.working_memory import WorkingMemory
from aura.core import AURA, AURABootOptions
from aura.events import EventBus
from aura.events.models import Event
from aura.telemetry import TelemetryManager, generate_runtime_report


class DummyEvent(Event):
    """Dummy event for testing event bus history capping."""

    def __init__(self, idx: int):
        self.idx = idx

    def event_name(self) -> str:
        return "DummyEvent"


def test_simulate_1000_interactions() -> None:
    """Simulates 1,000 interactions and asserts bounded buffer caps."""
    initial_threads = threading.active_count()

    tm = TelemetryManager.get_instance()
    tm.reset()

    bus = EventBus()
    wm = WorkingMemory(max_conversation_turns=12)

    # Simulate 1,000 interactions across all 3 subsystems
    for i in range(1000):
        # 1. Telemetry interaction
        tm.record_interaction(f"User test text iteration {i}", "RESPOND")
        tm.record_latency("time_turn_ms", 150.0 + (i % 10))

        # 2. EventBus event
        bus.publish(DummyEvent(i))

        # 3. WorkingMemory turn
        wm.add_conversation_turn(f"User message {i}", f"AURA response {i}")

    # Assert buffer caps strictly enforced
    assert len(tm.get_recent_interactions()) <= 100
    assert len(bus._history) <= 1000
    assert len(wm.get_recent_conversation()) <= 12

    # Assert thread stability (no leaked background threads created during recording)
    assert threading.active_count() == initial_threads


def test_telemetry_snapshot_export(tmp_path) -> None:
    """Verifies exporting TelemetryManager metrics to a JSON snapshot file."""
    tm = TelemetryManager.get_instance()
    tm.reset()
    tm.increment("llm_calls_total", 5)
    tm.record_latency("time_llm_ms", 1200.0)

    snap_file = tmp_path / "diagnostics" / "telemetry_snapshots" / "test_snapshot.json"
    snapshot_data = tm.export_snapshot(filepath=snap_file)

    assert snap_file.exists()
    assert snapshot_data["counters"]["llm_calls_total"] == 5
    assert "time_llm_ms" in snapshot_data["latencies"]
    assert snapshot_data["latencies"]["time_llm_ms"]["count"] == 1

    with open(snap_file, encoding="utf-8") as f:
        loaded = json.load(f)

    assert loaded["timestamp"] == snapshot_data["timestamp"]
    assert loaded["counters"]["llm_calls_total"] == 5


def test_runtime_diagnostics_report(tmp_path) -> None:
    """Verifies generation of runtime_report.json including SQLite page & WAL metrics."""
    db_file = tmp_path / "test_aura.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE test (id INT);")
    conn.execute("INSERT INTO test VALUES (1);")
    conn.commit()
    conn.close()

    report_file = tmp_path / "runtime_report.json"
    report_data = generate_runtime_report(db_path=str(db_file), filepath=report_file)

    assert report_file.exists()
    assert "uptime_seconds" in report_data
    assert "cpu_percent" in report_data
    assert "memory_rss_mb" in report_data
    assert "sqlite_db_size_bytes" in report_data
    assert report_data["sqlite_page_count"] > 0
    assert report_data["sqlite_page_size"] > 0
    assert "sqlite_wal_size_bytes" in report_data
    assert "telemetry_counters" in report_data

    with open(report_file, encoding="utf-8") as f:
        loaded = json.load(f)

    assert loaded["sqlite_page_count"] == report_data["sqlite_page_count"]


def test_cli_benchmark_command(capsys) -> None:
    """Verifies that _handle_benchmark prints the complete formatted benchmark report."""
    options = AURABootOptions(enable_audio=False, enable_vision=False)
    aura = AURA(options=options)
    aura.boot()

    try:
        tm = TelemetryManager.get_instance()
        tm.reset()
        tm.record_interaction("hola aura", "FASTPATH_GREETING")
        tm.increment("fastpath_greetings", 1)
        tm.record_latency("time_turn_ms", 12.0)

        _handle_benchmark(aura)
        captured = capsys.readouterr().out

        assert "AURA BENCHMARK REPORT" in captured
        assert "Average STT Latency:" in captured
        assert "Average Cognition Latency:" in captured
        assert "Average LLM Latency:" in captured
        assert "Average Turn Latency:" in captured
        assert "FastPath Hit Rate:" in captured
        assert "LLM Calls per Turn:" in captured
        assert "Memory Retrieval Success:" in captured
        assert "Total Interactions:" in captured
        assert "Total LLM Calls:" in captured
        assert "Total FastPaths:" in captured
    finally:
        aura.shutdown(wait=True)
