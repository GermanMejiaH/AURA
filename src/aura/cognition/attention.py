from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AttentionLevel(int, Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 8
    URGENT = 10


@dataclass
class AttentionItem:
    target: str
    priority: int = AttentionLevel.NORMAL.value
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)


class AttentionManager:
    """Filters incoming events and selects focus target based on priority (SPEC-001 Section 5.2)."""

    def __init__(self, default_threshold: int = AttentionLevel.LOW.value) -> None:
        self.threshold = default_threshold
        self._current_focus: AttentionItem | None = None
        self._lock = threading.RLock()

    @property
    def current_focus(self) -> AttentionItem | None:
        with self._lock:
            return self._current_focus

    def evaluate_event(
        self,
        event_name: str,
        payload: dict[str, Any],
        source: str = "",
    ) -> AttentionItem | None:
        with self._lock:
            priority = AttentionLevel.NORMAL.value

            # Wake word or user direct interaction
            if "wake" in event_name.lower() or "user" in event_name.lower():
                priority = AttentionLevel.URGENT.value
            elif "error" in event_name.lower() or "alarm" in event_name.lower():
                priority = AttentionLevel.HIGH.value

            if priority < self.threshold:
                return None

            item = AttentionItem(
                target=event_name,
                priority=priority,
                reason=f"Event from {source}",
                payload=payload,
            )

            if self._current_focus is None or priority >= self._current_focus.priority:
                self._current_focus = item

            return item

    def clear_focus(self) -> None:
        with self._lock:
            self._current_focus = None
