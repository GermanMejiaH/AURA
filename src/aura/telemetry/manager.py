"""Central TelemetryManager for AURA performance metrics and observability."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import InteractionRecord, LatencyMetric


class TelemetryManager:
    """Central thread-safe registry tracking counters, latencies, and interaction analytics."""

    _global_instance: TelemetryManager | None = None
    _instance_lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> TelemetryManager:
        """Retrieves or creates the global fallback TelemetryManager instance."""
        if cls._global_instance is None:
            with cls._instance_lock:
                if cls._global_instance is None:
                    cls._global_instance = TelemetryManager()
        return cls._global_instance

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, int] = {
            "llm_calls_total": 0,
            "llm_calls_success": 0,
            "llm_calls_failed": 0,
            "llm_rate_limit_429": 0,
            "fastpath_greetings": 0,
            "fastpath_memory_queries": 0,
            "fastpath_exit_commands": 0,
            "memory_retrievals": 0,
            "memory_writes": 0,
            "speech_events_detected": 0,
            "autonomy_cycles": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "max_prompt_tokens": 0,
            "max_completion_tokens": 0,
            "token_record_count": 0,
        }
        self._latencies: dict[str, LatencyMetric] = {
            "time_stt_ms": LatencyMetric("time_stt_ms"),
            "time_cognition_ms": LatencyMetric("time_cognition_ms"),
            "time_llm_ms": LatencyMetric("time_llm_ms"),
            "time_memory_ms": LatencyMetric("time_memory_ms"),
            "time_tts_ms": LatencyMetric("time_tts_ms"),
            "time_turn_ms": LatencyMetric("time_turn_ms"),
        }
        self._interactions: list[InteractionRecord] = []
        self._max_interactions: int = 100

    def record_token_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Records token usage for LLM calls thread-safely."""
        with self._lock:
            self._counters["total_prompt_tokens"] = (
                self._counters.get("total_prompt_tokens", 0) + prompt_tokens
            )
            self._counters["total_completion_tokens"] = (
                self._counters.get("total_completion_tokens", 0) + completion_tokens
            )
            self._counters["token_record_count"] = self._counters.get("token_record_count", 0) + 1
            if prompt_tokens > self._counters.get("max_prompt_tokens", 0):
                self._counters["max_prompt_tokens"] = prompt_tokens
            if completion_tokens > self._counters.get("max_completion_tokens", 0):
                self._counters["max_completion_tokens"] = completion_tokens

    def get_token_stats(self) -> dict[str, Any]:
        """Returns token usage summary metrics (avg and max)."""
        with self._lock:
            cnt = self._counters.get("token_record_count", 0)
            tot_p = self._counters.get("total_prompt_tokens", 0)
            tot_c = self._counters.get("total_completion_tokens", 0)
            avg_p = round(tot_p / cnt, 1) if cnt > 0 else 0.0
            avg_c = round(tot_c / cnt, 1) if cnt > 0 else 0.0
            return {
                "avg_prompt_tokens": avg_p,
                "avg_completion_tokens": avg_c,
                "max_prompt_tokens": self._counters.get("max_prompt_tokens", 0),
                "max_completion_tokens": self._counters.get("max_completion_tokens", 0),
                "total_prompt_tokens": tot_p,
                "total_completion_tokens": tot_c,
                "token_record_count": cnt,
            }

    def increment(self, metric_name: str, amount: int = 1) -> None:
        """Increments a counter metric thread-safely."""
        with self._lock:
            self._counters[metric_name] = self._counters.get(metric_name, 0) + amount

    def get_counter(self, metric_name: str) -> int:
        """Retrieves current value for a counter metric."""
        with self._lock:
            return self._counters.get(metric_name, 0)

    def get_all_counters(self) -> dict[str, int]:
        """Returns a copy of all counter values."""
        with self._lock:
            return dict(self._counters)

    def record_latency(self, metric_name: str, elapsed_ms: float) -> None:
        """Records a latency duration measurement in milliseconds."""
        with self._lock:
            if metric_name not in self._latencies:
                self._latencies[metric_name] = LatencyMetric(metric_name)
            self._latencies[metric_name].update(elapsed_ms)

    def get_latency_summary(self, metric_name: str) -> LatencyMetric | None:
        """Returns the latency metric summary for a metric name."""
        with self._lock:
            metric = self._latencies.get(metric_name)
            if metric is None:
                return None
            return LatencyMetric(
                metric_name=metric.metric_name,
                count=metric.count,
                total_ms=metric.total_ms,
                min_ms=metric.min_ms,
                max_ms=metric.max_ms,
            )

    def get_all_latencies(self) -> dict[str, LatencyMetric]:
        """Returns copies of all latency metric summaries."""
        with self._lock:
            return {
                name: LatencyMetric(
                    metric_name=m.metric_name,
                    count=m.count,
                    total_ms=m.total_ms,
                    min_ms=m.min_ms,
                    max_ms=m.max_ms,
                )
                for name, m in self._latencies.items()
            }

    def record_interaction(self, input_text: str, decision_type: str) -> None:
        """Records an AUTO mode interaction decision."""
        with self._lock:
            rec = InteractionRecord(input_text=input_text, decision_type=decision_type)
            self._interactions.append(rec)
            if len(self._interactions) > self._max_interactions:
                self._interactions.pop(0)

            # Automatically increment decision-specific counter
            decision_metric = f"decision_{decision_type.lower()}_count"
            self._counters[decision_metric] = self._counters.get(decision_metric, 0) + 1

    def get_recent_interactions(self) -> list[InteractionRecord]:
        """Returns recent interaction records."""
        with self._lock:
            return list(self._interactions)

    def reset(self) -> None:
        """Resets all metrics and interaction records."""
        with self._lock:
            for key in self._counters:
                self._counters[key] = 0
            for key in self._latencies:
                self._latencies[key] = LatencyMetric(key)
            self._interactions.clear()

    def get_performance_report(self) -> str:
        """Generates formatted AURA PERFORMANCE REPORT according to Stage 25.5 specification."""
        with self._lock:
            llm_total = self._counters.get("llm_calls_total", 0)
            llm_success = self._counters.get("llm_calls_success", 0)
            llm_failed = self._counters.get("llm_calls_failed", 0)
            llm_429 = self._counters.get("llm_rate_limit_429", 0)

            greetings_fp = self._counters.get("fastpath_greetings", 0)
            memory_fp = self._counters.get("fastpath_memory_queries", 0)

            avg_stt = (
                round(self._latencies["time_stt_ms"].avg_ms)
                if "time_stt_ms" in self._latencies
                else 0
            )
            avg_cog = (
                round(self._latencies["time_cognition_ms"].avg_ms)
                if "time_cognition_ms" in self._latencies
                else 0
            )
            avg_llm = (
                round(self._latencies["time_llm_ms"].avg_ms)
                if "time_llm_ms" in self._latencies
                else 0
            )
            avg_turn = (
                round(self._latencies["time_turn_ms"].avg_ms)
                if "time_turn_ms" in self._latencies
                else 0
            )

            mem_writes = self._counters.get("memory_writes", 0)
            mem_reads = self._counters.get("memory_retrievals", 0)

        lines = [
            "===================================",
            "AURA PERFORMANCE REPORT",
            "===================================",
            f"LLM Calls: {llm_total}",
            f"Successful: {llm_success}",
            f"Failed: {llm_failed}",
            f"429 Events: {llm_429}",
            "",
            f"Greetings FastPath: {greetings_fp}",
            f"Memory FastPath: {memory_fp}",
            "",
            "Average STT:",
            f"{avg_stt} ms",
            "",
            "Average Cognition:",
            f"{avg_cog} ms",
            "",
            "Average LLM:",
            f"{avg_llm} ms",
            "",
            "Average Turn:",
            f"{avg_turn} ms",
            "",
            "Memory Writes:",
            f"{mem_writes}",
            "",
            "Memory Reads:",
            f"{mem_reads}",
            "===================================",
        ]
        return "\n".join(lines)

    def export_snapshot(self, filepath: str | Path | None = None) -> dict[str, Any]:
        """Exports current TelemetryManager metrics to a JSON snapshot file."""
        import json

        with self._lock:
            ts_str = datetime.now(UTC).isoformat()
            latencies_dict = {}
            for name, m in self._latencies.items():
                latencies_dict[name] = {
                    "count": m.count,
                    "total_ms": round(m.total_ms, 2),
                    "avg_ms": round(m.avg_ms, 2),
                    "min_ms": round(m.min_ms, 2) if m.min_ms != float("inf") else 0.0,
                    "max_ms": round(m.max_ms, 2),
                }

            snapshot_data: dict[str, Any] = {
                "timestamp": ts_str,
                "counters": dict(self._counters),
                "latencies": latencies_dict,
                "token_stats": self.get_token_stats(),
                "recent_interactions_count": len(self._interactions),
            }

        if filepath is None:
            ts_compact = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            target_path = (
                Path("diagnostics")
                / "telemetry_snapshots"
                / f"telemetry_snapshot_{ts_compact}.json"
            )
        else:
            target_path = Path(filepath)

        target_path.parent.mkdir(parents=True, exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2, ensure_ascii=False)

        return snapshot_data
