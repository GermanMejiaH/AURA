"""Telemetry data models for AURA performance observability."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LatencyMetric:
    """Aggregated latency metric recording count, min, max, and running average."""

    metric_name: str
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0

    @property
    def avg_ms(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_ms / self.count

    def update(self, elapsed_ms: float) -> None:
        self.count += 1
        self.total_ms += elapsed_ms
        if elapsed_ms < self.min_ms:
            self.min_ms = elapsed_ms
        if elapsed_ms > self.max_ms:
            self.max_ms = elapsed_ms

    def to_dict(self) -> dict[str, Any]:
        min_val = 0.0 if self.min_ms == float("inf") else self.min_ms
        return {
            "count": self.count,
            "avg_ms": round(self.avg_ms, 2),
            "min_ms": round(min_val, 2),
            "max_ms": round(self.max_ms, 2),
        }


@dataclass
class InteractionRecord:
    """Record of an AUTO mode interaction turn."""

    input_text: str
    decision_type: str  # RESPOND, IGNORE, ACT, FASTPATH_GREETING, FASTPATH_MEMORY, EXIT
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_text": self.input_text,
            "decision_type": self.decision_type,
            "timestamp": self.timestamp,
        }
