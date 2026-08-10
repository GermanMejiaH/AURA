from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class WorkingMemoryItem:
    key: str
    value: Any
    ttl_seconds: float = 300.0
    created_at: datetime = field(default_factory=_utcnow)

    @property
    def is_expired(self) -> bool:
        return _utcnow() > self.created_at + timedelta(seconds=self.ttl_seconds)


class WorkingMemory:
    """Short-term working memory containing transient cognitive context (SPEC-001 Section 5.3)."""

    def __init__(
        self,
        default_ttl_seconds: float = 300.0,
        max_conversation_turns: int = 12,
    ) -> None:
        self.default_ttl = default_ttl_seconds
        self.max_conversation_turns = max_conversation_turns
        self._items: dict[str, WorkingMemoryItem] = {}
        self._conversation_history: list[dict[str, str]] = []
        self._active_goal: str | None = None
        self._lock = threading.RLock()

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        with self._lock:
            ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
            self._items[key] = WorkingMemoryItem(key=key, value=value, ttl_seconds=ttl)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return default
            if item.is_expired:
                del self._items[key]
                return default
            return item.value

    def add_conversation_turn(self, role: str, content: str) -> None:
        with self._lock:
            self._conversation_history.append({"role": role, "content": content})
            if len(self._conversation_history) > self.max_conversation_turns:
                self._conversation_history = self._conversation_history[
                    -self.max_conversation_turns :
                ]

    def get_recent_conversation(self, limit: int | None = None) -> list[dict[str, str]]:
        with self._lock:
            if limit is None:
                return list(self._conversation_history)
            return list(self._conversation_history[-limit:])

    def set_active_goal(self, goal: str | None) -> None:
        with self._lock:
            self._active_goal = goal

    @property
    def active_goal(self) -> str | None:
        with self._lock:
            return self._active_goal

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._conversation_history.clear()
            self._active_goal = None
