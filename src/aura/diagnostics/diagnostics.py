from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..events import EventBus
from ..logging import get_logger


@dataclass
class ErrorRecord:
    timestamp: datetime
    module: str
    error_type: str
    message: str
    recoverable: bool = True
    handled: bool = False


@dataclass
class Diagnostics:
    event_bus: EventBus | None = None
    module_manager: Any = None
    lifecycle: Any = None

    _boot_started_at: datetime | None = None
    _boot_completed_at: datetime | None = None
    _shutdown_started_at: datetime | None = None
    _errors: list[ErrorRecord] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _max_errors: int = 500

    def mark_boot_started(self) -> None:
        self._boot_started_at = datetime.now(UTC)
        logger = get_logger("Diagnostics")
        logger.info("Boot sequence started")

    def mark_boot_completed(self) -> None:
        self._boot_completed_at = datetime.now(UTC)
        logger = get_logger("Diagnostics")
        if self._boot_started_at is not None:
            elapsed = (self._boot_completed_at - self._boot_started_at).total_seconds()
            logger.info(f"Boot sequence completed in {elapsed:.3f}s")
        else:
            logger.info("Boot sequence completed")

    def mark_shutdown_started(self) -> None:
        self._shutdown_started_at = datetime.now(UTC)
        logger = get_logger("Diagnostics")
        logger.info("Shutdown sequence started")

    @property
    def boot_duration_seconds(self) -> float | None:
        if self._boot_started_at is None or self._boot_completed_at is None:
            return None
        return (self._boot_completed_at - self._boot_started_at).total_seconds()

    def record_error(
        self,
        module: str,
        error_type: str,
        message: str,
        *,
        recoverable: bool = True,
    ) -> None:
        with self._lock:
            self._errors.append(
                ErrorRecord(
                    timestamp=datetime.now(UTC),
                    module=module,
                    error_type=error_type,
                    message=message,
                    recoverable=recoverable,
                )
            )
            if len(self._errors) > self._max_errors:
                self._errors = self._errors[-self._max_errors :]

    def recent_errors(self, limit: int = 20) -> list[ErrorRecord]:
        with self._lock:
            return list(self._errors[-limit:])

    def error_count(self, since: datetime | None = None) -> int:
        with self._lock:
            if since is None:
                return len(self._errors)
            return sum(1 for e in self._errors if e.timestamp >= since)

    def collect_snapshot(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "boot": {
                "started_at": (
                    self._boot_started_at.isoformat() if self._boot_started_at else None
                ),
                "completed_at": (
                    self._boot_completed_at.isoformat()
                    if self._boot_completed_at
                    else None
                ),
                "duration_seconds": self.boot_duration_seconds,
            },
            "errors": {
                "total": len(self._errors),
                "recent": [
                    {
                        "timestamp": e.timestamp.isoformat(),
                        "module": e.module,
                        "type": e.error_type,
                        "message": e.message,
                        "recoverable": e.recoverable,
                    }
                    for e in self._errors[-10:]
                ],
            },
        }

        if self.lifecycle is not None:
            try:
                data["lifecycle"] = {
                    "state": self.lifecycle.state.value,
                    "uptime_seconds": self.lifecycle.uptime_seconds,
                }
            except Exception:
                pass

        if self.module_manager is not None:
            try:
                modules_snapshot = self.module_manager.health_snapshot()
                data["modules"] = {
                    "total": len(modules_snapshot),
                    "details": {
                        name: {
                            "status": mod.status.value,
                            "last_error": mod.last_error,
                            "started_at": mod.started_at,
                        }
                        for name, mod in modules_snapshot.items()
                    },
                }
            except Exception:
                pass

        if self.event_bus is not None:
            try:
                data["event_bus"] = {
                    "history_size": len(self.event_bus.history()),
                    "subscribers": self.event_bus.subscriber_count(),
                }
            except Exception:
                pass

        return data

    def formatted_report(self) -> str:
        snap = self.collect_snapshot()
        lines: list[str] = []
        lines.append("=== AURA Diagnostics Report ===")
        lines.append(f"Timestamp: {snap['timestamp']}")
        if snap.get("lifecycle"):
            lc = snap["lifecycle"]
            lines.append(f"State: {lc['state']}")
            lines.append(f"Uptime: {lc['uptime_seconds']:.2f}s")
        if snap.get("boot"):
            b = snap["boot"]
            if b["duration_seconds"] is not None:
                lines.append(f"Boot duration: {b['duration_seconds']:.3f}s")
        if snap.get("modules"):
            m = snap["modules"]
            lines.append(f"Modules: {m['total']} registered")
            for name, info in m["details"].items():
                lines.append(f"  - {name}: {info['status']}")
        if snap.get("errors"):
            e = snap["errors"]
            lines.append(f"Errors: {e['total']} total")
        lines.append("==================================")
        return "\n".join(lines)
