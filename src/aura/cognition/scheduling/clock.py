from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Protocol defining the clock interface for time resolution across AURA scheduling."""

    def now(self) -> datetime: ...

    def now_iso(self) -> str: ...


class SystemClock:
    """Real system clock implementation returning current UTC datetime."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def now_iso(self) -> str:
        return datetime.now(UTC).isoformat()


class TestClock:
    """Controllable test clock for instant, deterministic fast-forwarding in unit tests."""

    __test__ = False

    def __init__(self, initial_time: datetime | str | None = None) -> None:
        self._lock = threading.RLock()
        if initial_time is None:
            self._current = datetime.now(UTC)
        elif isinstance(initial_time, str):
            dt = datetime.fromisoformat(initial_time.strip())
            if dt.tzinfo is None:
                self._current = dt.replace(tzinfo=UTC)
            else:
                self._current = dt.astimezone(UTC)
        else:
            if initial_time.tzinfo is None:
                self._current = initial_time.replace(tzinfo=UTC)
            else:
                self._current = initial_time.astimezone(UTC)

    def now(self) -> datetime:
        with self._lock:
            return self._current

    def now_iso(self) -> str:
        with self._lock:
            return self._current.isoformat()

    def set_time(self, dt: datetime | str) -> None:
        """Sets the current test time directly to a datetime or ISO string."""
        with self._lock:
            if isinstance(dt, str):
                parsed = datetime.fromisoformat(dt.strip())
                if parsed.tzinfo is None:
                    self._current = parsed.replace(tzinfo=UTC)
                else:
                    self._current = parsed.astimezone(UTC)
            else:
                if dt.tzinfo is None:
                    self._current = dt.replace(tzinfo=UTC)
                else:
                    self._current = dt.astimezone(UTC)

    def advance(self, seconds: float | timedelta) -> None:
        """Advances the test clock time by seconds or timedelta instantly without sleep."""
        delta = seconds if isinstance(seconds, timedelta) else timedelta(seconds=float(seconds))
        with self._lock:
            self._current += delta
