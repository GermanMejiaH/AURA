from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from aura.events import (
    Event,
    EventBus,
    RuntimeStatePersisted,
    RuntimeStateRestored,
    RuntimeUnexpectedShutdownDetected,
)
from aura.logging import get_logger
from aura.memory.store import SQLiteMemoryStore

logger = get_logger("RuntimeHistoryStore")


@dataclass
class RuntimeStateRecord:
    """Durable state record for an autonomy runtime instance."""

    runtime_name: str
    status: str
    started_at: str | None = None
    stopped_at: str | None = None
    last_tick_at: str | None = None
    last_successful_tick_at: str | None = None
    last_failed_tick_at: str | None = None
    tick_count: int = 0
    successful_ticks: int = 0
    failed_ticks: int = 0
    skipped_overlapping_ticks: int = 0
    last_error: str | None = None
    recovery_attempts_count: int = 0
    last_recovery_at: str | None = None
    recovery_failures_count: int = 0
    updated_at: str = ""


@dataclass
class RuntimeEventRecord:
    """Durable historical event record for autonomy runtime observability."""

    event_id: str
    runtime_name: str
    event_type: str
    event_timestamp: str
    payload_json: str
    created_at: str

    @property
    def payload(self) -> dict[str, Any]:
        try:
            return json.loads(self.payload_json)  # type: ignore[no-any-return]
        except Exception:
            return {}


@dataclass
class RuntimeAggregateStats:
    """Aggregated historical statistics for autonomy runtime observability."""

    runtime_name: str
    total_boots: int = 0
    total_shutdowns: int = 0
    total_ticks: int = 0
    total_successful_ticks: int = 0
    total_failed_ticks: int = 0
    total_skipped_ticks: int = 0
    total_recovery_attempts: int = 0
    total_recovery_failures: int = 0
    interrupted_runs_count: int = 0
    last_error: str | None = None
    last_recovery_at: str | None = None


class RuntimeHistoryStore:
    """Persistence repository for autonomy runtime state and event history using SQLite."""

    def __init__(
        self,
        db_path: str = "data/aura.db",
        store: SQLiteMemoryStore | None = None,
        max_events: int = 1000,
    ) -> None:
        if store is not None:
            self._memory_store = store
            self.db_path = store.db_path
        else:
            self._memory_store = SQLiteMemoryStore(db_path=db_path)
            self.db_path = db_path

        self._lock: threading.RLock = self._memory_store._lock
        self.max_events = max_events
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return self._memory_store._get_connection()

    def _init_db(self) -> None:
        with self._lock:
            try:
                conn = self._get_connection()
                with conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS autonomy_runtime_state (
                            runtime_name TEXT PRIMARY KEY,
                            status TEXT NOT NULL,
                            started_at TEXT,
                            stopped_at TEXT,
                            last_tick_at TEXT,
                            last_successful_tick_at TEXT,
                            last_failed_tick_at TEXT,
                            tick_count INTEGER NOT NULL DEFAULT 0,
                            successful_ticks INTEGER NOT NULL DEFAULT 0,
                            failed_ticks INTEGER NOT NULL DEFAULT 0,
                            skipped_overlapping_ticks INTEGER NOT NULL DEFAULT 0,
                            last_error TEXT,
                            recovery_attempts_count INTEGER NOT NULL DEFAULT 0,
                            last_recovery_at TEXT,
                            recovery_failures_count INTEGER NOT NULL DEFAULT 0,
                            updated_at TEXT NOT NULL
                        )
                        """
                    )
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS autonomy_runtime_events (
                            event_id TEXT PRIMARY KEY,
                            runtime_name TEXT NOT NULL,
                            event_type TEXT NOT NULL,
                            event_timestamp TEXT NOT NULL,
                            payload_json TEXT NOT NULL DEFAULT '{}',
                            created_at TEXT NOT NULL
                        )
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_runtime_events_name_type
                        ON autonomy_runtime_events(runtime_name, event_type)
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_runtime_events_timestamp
                        ON autonomy_runtime_events(event_timestamp)
                        """
                    )
            except Exception as exc:
                logger.error(
                    f"Failed to initialize autonomy runtime tables in '{self.db_path}': {exc}"
                )

    def save_state(self, record: RuntimeStateRecord) -> None:
        """Saves or updates a RuntimeStateRecord in SQLite safely."""
        with self._lock:
            try:
                now_iso = record.updated_at or datetime.now(UTC).isoformat()
                conn = self._get_connection()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO autonomy_runtime_state (
                            runtime_name, status, started_at, stopped_at,
                            last_tick_at, last_successful_tick_at, last_failed_tick_at,
                            tick_count, successful_ticks, failed_ticks, skipped_overlapping_ticks,
                            last_error, recovery_attempts_count, last_recovery_at,
                            recovery_failures_count, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(runtime_name) DO UPDATE SET
                            status=excluded.status,
                            started_at=COALESCE(excluded.started_at, started_at),
                            stopped_at=excluded.stopped_at,
                            last_tick_at=COALESCE(excluded.last_tick_at, last_tick_at),
                            last_successful_tick_at=COALESCE(
                                excluded.last_successful_tick_at, last_successful_tick_at
                            ),
                            last_failed_tick_at=COALESCE(
                                excluded.last_failed_tick_at, last_failed_tick_at
                            ),
                            tick_count=excluded.tick_count,
                            successful_ticks=excluded.successful_ticks,
                            failed_ticks=excluded.failed_ticks,
                            skipped_overlapping_ticks=excluded.skipped_overlapping_ticks,
                            last_error=excluded.last_error,
                            recovery_attempts_count=excluded.recovery_attempts_count,
                            last_recovery_at=COALESCE(excluded.last_recovery_at, last_recovery_at),
                            recovery_failures_count=excluded.recovery_failures_count,
                            updated_at=excluded.updated_at
                        """,
                        (
                            record.runtime_name,
                            record.status,
                            record.started_at,
                            record.stopped_at,
                            record.last_tick_at,
                            record.last_successful_tick_at,
                            record.last_failed_tick_at,
                            record.tick_count,
                            record.successful_ticks,
                            record.failed_ticks,
                            record.skipped_overlapping_ticks,
                            record.last_error,
                            record.recovery_attempts_count,
                            record.last_recovery_at,
                            record.recovery_failures_count,
                            now_iso,
                        ),
                    )
            except Exception as exc:
                logger.warning(f"Failed to save runtime state for '{record.runtime_name}': {exc}")

    def get_state(self, runtime_name: str) -> RuntimeStateRecord | None:
        """Retrieves the latest persisted RuntimeStateRecord for a given runtime name."""
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.execute(
                    "SELECT * FROM autonomy_runtime_state WHERE runtime_name = ?",
                    (runtime_name,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return RuntimeStateRecord(
                    runtime_name=row["runtime_name"],
                    status=row["status"],
                    started_at=row["started_at"],
                    stopped_at=row["stopped_at"],
                    last_tick_at=row["last_tick_at"],
                    last_successful_tick_at=row["last_successful_tick_at"],
                    last_failed_tick_at=row["last_failed_tick_at"],
                    tick_count=row["tick_count"],
                    successful_ticks=row["successful_ticks"],
                    failed_ticks=row["failed_ticks"],
                    skipped_overlapping_ticks=row["skipped_overlapping_ticks"],
                    last_error=row["last_error"],
                    recovery_attempts_count=row["recovery_attempts_count"],
                    last_recovery_at=row["last_recovery_at"],
                    recovery_failures_count=row["recovery_failures_count"],
                    updated_at=row["updated_at"],
                )
            except Exception as exc:
                logger.warning(f"Failed to get runtime state for '{runtime_name}': {exc}")
                return None

    def record_event(
        self,
        runtime_name: str,
        event_type: str,
        event_timestamp: str,
        payload: dict[str, Any],
    ) -> None:
        """Records a historical runtime event in SQLite safely."""
        with self._lock:
            try:
                event_id = str(uuid.uuid4())
                now_iso = datetime.now(UTC).isoformat()
                payload_json = json.dumps(payload, default=str)
                conn = self._get_connection()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO autonomy_runtime_events (
                            event_id, runtime_name, event_type,
                            event_timestamp, payload_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            runtime_name,
                            event_type,
                            event_timestamp,
                            payload_json,
                            now_iso,
                        ),
                    )
                self.prune_events(self.max_events)
            except Exception as exc:
                logger.warning(f"Failed to record event '{event_type}' for '{runtime_name}': {exc}")

    def get_event_history(
        self,
        runtime_name: str,
        limit: int = 50,
        event_type: str | None = None,
    ) -> list[RuntimeEventRecord]:
        """Queries historical runtime events filtered by runtime_name and optional event_type."""
        with self._lock:
            try:
                query = "SELECT * FROM autonomy_runtime_events WHERE runtime_name = ?"
                params: list[Any] = [runtime_name]

                if event_type is not None:
                    query += " AND event_type = ?"
                    params.append(event_type)

                query += " ORDER BY event_timestamp DESC, created_at DESC LIMIT ?"
                params.append(limit)

                conn = self._get_connection()
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

                return [
                    RuntimeEventRecord(
                        event_id=r["event_id"],
                        runtime_name=r["runtime_name"],
                        event_type=r["event_type"],
                        event_timestamp=r["event_timestamp"],
                        payload_json=r["payload_json"],
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]
            except Exception as exc:
                logger.warning(f"Failed to query event history for '{runtime_name}': {exc}")
                return []

    def get_recovery_history(self, runtime_name: str, limit: int = 50) -> list[RuntimeEventRecord]:
        """Queries historical recovery events (Attempted, Recovered, Failed)."""
        with self._lock:
            try:
                query = """
                SELECT * FROM autonomy_runtime_events
                WHERE runtime_name = ? AND event_type IN (
                    'RuntimeRecoveryAttempted', 'RuntimeRecovered', 'RuntimeRecoveryFailed'
                )
                ORDER BY event_timestamp DESC, created_at DESC LIMIT ?
                """
                conn = self._get_connection()
                cursor = conn.execute(query, (runtime_name, limit))
                rows = cursor.fetchall()
                return [
                    RuntimeEventRecord(
                        event_id=r["event_id"],
                        runtime_name=r["runtime_name"],
                        event_type=r["event_type"],
                        event_timestamp=r["event_timestamp"],
                        payload_json=r["payload_json"],
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]
            except Exception as exc:
                logger.warning(f"Failed to query recovery history for '{runtime_name}': {exc}")
                return []

    def get_failed_ticks(self, runtime_name: str, limit: int = 50) -> list[RuntimeEventRecord]:
        """Queries historical failed tick events."""
        return self.get_event_history(
            runtime_name=runtime_name, limit=limit, event_type="RuntimeTickFailed"
        )

    def get_aggregate_stats(self, runtime_name: str) -> RuntimeAggregateStats:
        """Computes aggregate historical statistics from persisted records and events."""
        with self._lock:
            try:
                state = self.get_state(runtime_name)
                conn = self._get_connection()

                boots = conn.execute(
                    """
                    SELECT COUNT(*) FROM autonomy_runtime_events
                    WHERE runtime_name = ? AND event_type = 'RuntimeStarted'
                    """,
                    (runtime_name,),
                ).fetchone()[0]

                shutdowns = conn.execute(
                    """
                    SELECT COUNT(*) FROM autonomy_runtime_events
                    WHERE runtime_name = ? AND event_type = 'RuntimeStopped'
                    """,
                    (runtime_name,),
                ).fetchone()[0]

                rec_attempts = conn.execute(
                    """
                    SELECT COUNT(*) FROM autonomy_runtime_events
                    WHERE runtime_name = ? AND event_type = 'RuntimeRecoveryAttempted'
                    """,
                    (runtime_name,),
                ).fetchone()[0]

                rec_failures = conn.execute(
                    """
                    SELECT COUNT(*) FROM autonomy_runtime_events
                    WHERE runtime_name = ? AND event_type = 'RuntimeRecoveryFailed'
                    """,
                    (runtime_name,),
                ).fetchone()[0]

                interrupted = conn.execute(
                    """
                    SELECT COUNT(*) FROM autonomy_runtime_events
                    WHERE runtime_name = ? AND event_type = 'InterruptedRunDetected'
                    """,
                    (runtime_name,),
                ).fetchone()[0]

                return RuntimeAggregateStats(
                    runtime_name=runtime_name,
                    total_boots=boots,
                    total_shutdowns=shutdowns,
                    total_ticks=state.tick_count if state else 0,
                    total_successful_ticks=state.successful_ticks if state else 0,
                    total_failed_ticks=state.failed_ticks if state else 0,
                    total_skipped_ticks=state.skipped_overlapping_ticks if state else 0,
                    total_recovery_attempts=rec_attempts,
                    total_recovery_failures=rec_failures,
                    interrupted_runs_count=interrupted,
                    last_error=state.last_error if state else None,
                    last_recovery_at=state.last_recovery_at if state else None,
                )
            except Exception as exc:
                logger.warning(f"Failed to compute aggregate stats for '{runtime_name}': {exc}")
                return RuntimeAggregateStats(runtime_name=runtime_name)

    def detect_interrupted_run(self, runtime_name: str) -> bool:
        """Determines if the previous process crashed or exited without clean shutdown."""
        with self._lock:
            try:
                state = self.get_state(runtime_name)
                is_interrupted = False
                if state is not None and state.status in {"started", "degraded"}:
                    events = self.get_event_history(runtime_name, limit=1)
                    if events and events[0].event_type != "RuntimeStopped":
                        is_interrupted = True
                    elif not events and state.stopped_at is None:
                        is_interrupted = True
            except Exception as exc:
                logger.warning(f"Failed to detect interrupted run for '{runtime_name}': {exc}")
                return False
            else:
                return is_interrupted

    def prune_events(self, max_events: int = 1000) -> int:
        """Prunes historical events exceeding max_events threshold to prevent database bloat."""
        with self._lock:
            try:
                conn = self._get_connection()
                with conn:
                    cursor = conn.execute(
                        """
                        DELETE FROM autonomy_runtime_events
                        WHERE event_id NOT IN (
                            SELECT event_id FROM autonomy_runtime_events
                            ORDER BY event_timestamp DESC, created_at DESC
                            LIMIT ?
                        )
                        """,
                        (max_events,),
                    )
                    return cursor.rowcount
            except Exception as exc:
                logger.warning(f"Failed to prune autonomy_runtime_events: {exc}")
                return 0


class RuntimePersistenceHandler:
    """Subscribes to EventBus runtime events and mirrors state/history to RuntimeHistoryStore."""

    def __init__(self, store: RuntimeHistoryStore, event_bus: EventBus) -> None:
        self.store = store
        self.event_bus = event_bus

        event_bus.subscribe("RuntimeStarted", self._on_runtime_started)
        event_bus.subscribe("RuntimeStopped", self._on_runtime_stopped)
        event_bus.subscribe("RuntimeTickCompleted", self._on_tick_completed)
        event_bus.subscribe("RuntimeTickFailed", self._on_tick_failed)
        event_bus.subscribe("RuntimeHealthChanged", self._on_health_changed)
        event_bus.subscribe("RuntimeRecoveryAttempted", self._on_recovery_attempted)
        event_bus.subscribe("RuntimeRecovered", self._on_recovered)
        event_bus.subscribe("RuntimeRecoveryFailed", self._on_recovery_failed)

    def _event_to_dict(self, event: Event) -> dict[str, Any]:
        if hasattr(event, "__dataclass_fields__"):
            return asdict(event)
        return dict(getattr(event, "payload", {}))

    def _on_runtime_started(self, event: Event) -> None:
        payload = self._event_to_dict(event)
        name = payload.get("runtime_name", "AuraAutonomyRuntime")
        ts = payload.get("started_at") or datetime.now(UTC).isoformat()

        self.store.record_event(name, "RuntimeStarted", ts, payload)
        state = self.store.get_state(name) or RuntimeStateRecord(
            runtime_name=name, status="started"
        )
        state.status = "started"
        state.started_at = ts
        state.stopped_at = None
        self.store.save_state(state)

    def _on_runtime_stopped(self, event: Event) -> None:
        payload = self._event_to_dict(event)
        name = payload.get("runtime_name", "AuraAutonomyRuntime")
        ts = payload.get("stopped_at") or datetime.now(UTC).isoformat()
        ticks = payload.get("tick_count", 0)

        self.store.record_event(name, "RuntimeStopped", ts, payload)
        state = self.store.get_state(name) or RuntimeStateRecord(
            runtime_name=name, status="stopped"
        )
        state.status = "stopped"
        state.stopped_at = ts
        state.tick_count = max(state.tick_count, ticks)
        self.store.save_state(state)

    def _on_tick_completed(self, event: Event) -> None:
        payload = self._event_to_dict(event)
        name = "AuraAutonomyRuntime"
        ts = payload.get("tick_timestamp") or datetime.now(UTC).isoformat()
        idx = payload.get("tick_index", 0)

        self.store.record_event(name, "RuntimeTickCompleted", ts, payload)
        state = self.store.get_state(name) or RuntimeStateRecord(
            runtime_name=name, status="started"
        )
        state.last_tick_at = ts
        state.last_successful_tick_at = ts
        state.tick_count = max(state.tick_count, idx)
        state.successful_ticks += 1
        self.store.save_state(state)

    def _on_tick_failed(self, event: Event) -> None:
        payload = self._event_to_dict(event)
        name = "AuraAutonomyRuntime"
        ts = payload.get("tick_timestamp") or datetime.now(UTC).isoformat()
        idx = payload.get("tick_index", 0)
        err = payload.get("error", "Unknown tick failure")

        self.store.record_event(name, "RuntimeTickFailed", ts, payload)
        state = self.store.get_state(name) or RuntimeStateRecord(
            runtime_name=name, status="started"
        )
        state.last_tick_at = ts
        state.last_failed_tick_at = ts
        state.tick_count = max(state.tick_count, idx)
        state.failed_ticks += 1
        state.last_error = str(err)
        self.store.save_state(state)

    def _on_health_changed(self, event: Event) -> None:
        payload = self._event_to_dict(event)
        name = payload.get("runtime_name", "AuraAutonomyRuntime")
        ts = datetime.now(UTC).isoformat()
        new_st = payload.get("new_status", "DEGRADED").lower()

        self.store.record_event(name, "RuntimeHealthChanged", ts, payload)
        state = self.store.get_state(name) or RuntimeStateRecord(runtime_name=name, status=new_st)
        state.status = new_st
        if payload.get("reason"):
            state.last_error = str(payload["reason"])
        self.store.save_state(state)

    def _on_recovery_attempted(self, event: Event) -> None:
        payload = self._event_to_dict(event)
        name = payload.get("runtime_name", "AuraAutonomyRuntime")
        ts = datetime.now(UTC).isoformat()

        self.store.record_event(name, "RuntimeRecoveryAttempted", ts, payload)
        state = self.store.get_state(name) or RuntimeStateRecord(
            runtime_name=name, status="recovering"
        )
        state.recovery_attempts_count += 1
        state.last_recovery_at = ts
        self.store.save_state(state)

    def _on_recovered(self, event: Event) -> None:
        payload = self._event_to_dict(event)
        name = payload.get("runtime_name", "AuraAutonomyRuntime")
        ts = payload.get("recovered_at") or datetime.now(UTC).isoformat()

        self.store.record_event(name, "RuntimeRecovered", ts, payload)
        state = self.store.get_state(name) or RuntimeStateRecord(
            runtime_name=name, status="started"
        )
        state.status = "started"
        state.last_recovery_at = ts
        state.last_error = None
        self.store.save_state(state)

    def _on_recovery_failed(self, event: Event) -> None:
        payload = self._event_to_dict(event)
        name = payload.get("runtime_name", "AuraAutonomyRuntime")
        ts = datetime.now(UTC).isoformat()

        self.store.record_event(name, "RuntimeRecoveryFailed", ts, payload)
        state = self.store.get_state(name) or RuntimeStateRecord(
            runtime_name=name, status="degraded"
        )
        state.status = "degraded"
        state.recovery_failures_count += 1
        if payload.get("reason"):
            state.last_error = str(payload["reason"])
        self.store.save_state(state)


@dataclass(frozen=True)
class PersistentRuntimeSnapshot:
    """Immutable persistent state snapshot for ContinuousAutonomyRuntime operational recovery."""

    runtime_name: str
    operational_state: str
    clean_shutdown: bool = False
    started_at: str | None = None
    stopped_at: str | None = None
    last_state_change_at: str | None = None
    last_state_change_reason: str | None = None
    last_tick_at: str | None = None
    last_successful_tick_at: str | None = None
    last_failed_tick_at: str | None = None
    last_error: str | None = None
    recovery_attempts: int = 0
    successful_recoveries: int = 0
    failed_recoveries: int = 0
    last_recovery_at: str | None = None
    degradation_reason: str | None = None
    updated_at: str = ""


class RuntimeStateStore:
    """Decoupled repository managing persistent runtime state and operational crash recovery."""

    def __init__(
        self,
        db_path: str = "data/aura.db",
        store: SQLiteMemoryStore | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        if store is not None:
            self._memory_store = store
            self.db_path = store.db_path
        else:
            self._memory_store = SQLiteMemoryStore(db_path=db_path)
            self.db_path = db_path

        self._lock: threading.RLock = self._memory_store._lock
        self.event_bus = event_bus
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return self._memory_store._get_connection()

    def _init_db(self) -> None:
        with self._lock:
            try:
                conn = self._get_connection()
                with conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS autonomy_persistent_state (
                            runtime_name TEXT PRIMARY KEY,
                            operational_state TEXT NOT NULL,
                            clean_shutdown INTEGER NOT NULL DEFAULT 0,
                            started_at TEXT,
                            stopped_at TEXT,
                            last_state_change_at TEXT,
                            last_state_change_reason TEXT,
                            last_tick_at TEXT,
                            last_successful_tick_at TEXT,
                            last_failed_tick_at TEXT,
                            last_error TEXT,
                            recovery_attempts INTEGER NOT NULL DEFAULT 0,
                            successful_recoveries INTEGER NOT NULL DEFAULT 0,
                            failed_recoveries INTEGER NOT NULL DEFAULT 0,
                            last_recovery_at TEXT,
                            degradation_reason TEXT,
                            updated_at TEXT NOT NULL
                        )
                        """
                    )
            except Exception as exc:
                logger.error(
                    f"Failed to initialize autonomy_persistent_state in '{self.db_path}': {exc}"
                )

    def save_snapshot(self, snapshot: PersistentRuntimeSnapshot) -> None:
        """Persists a PersistentRuntimeSnapshot to SQLite atomically."""
        with self._lock:
            try:
                now_iso = snapshot.updated_at or datetime.now(UTC).isoformat()
                conn = self._get_connection()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO autonomy_persistent_state (
                            runtime_name, operational_state, clean_shutdown,
                            started_at, stopped_at, last_state_change_at, last_state_change_reason,
                            last_tick_at, last_successful_tick_at, last_failed_tick_at,
                            last_error, recovery_attempts, successful_recoveries, failed_recoveries,
                            last_recovery_at, degradation_reason, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(runtime_name) DO UPDATE SET
                            operational_state=excluded.operational_state,
                            clean_shutdown=excluded.clean_shutdown,
                            started_at=COALESCE(excluded.started_at, started_at),
                            stopped_at=excluded.stopped_at,
                            last_state_change_at=COALESCE(
                                excluded.last_state_change_at, last_state_change_at
                            ),
                            last_state_change_reason=COALESCE(
                                excluded.last_state_change_reason, last_state_change_reason
                            ),
                            last_tick_at=COALESCE(excluded.last_tick_at, last_tick_at),
                            last_successful_tick_at=COALESCE(
                                excluded.last_successful_tick_at, last_successful_tick_at
                            ),
                            last_failed_tick_at=COALESCE(
                                excluded.last_failed_tick_at, last_failed_tick_at
                            ),
                            last_error=excluded.last_error,
                            recovery_attempts=excluded.recovery_attempts,
                            successful_recoveries=excluded.successful_recoveries,
                            failed_recoveries=excluded.failed_recoveries,
                            last_recovery_at=COALESCE(excluded.last_recovery_at, last_recovery_at),
                            degradation_reason=excluded.degradation_reason,
                            updated_at=excluded.updated_at
                        """,
                        (
                            snapshot.runtime_name,
                            snapshot.operational_state,
                            1 if snapshot.clean_shutdown else 0,
                            snapshot.started_at,
                            snapshot.stopped_at,
                            snapshot.last_state_change_at,
                            snapshot.last_state_change_reason,
                            snapshot.last_tick_at,
                            snapshot.last_successful_tick_at,
                            snapshot.last_failed_tick_at,
                            snapshot.last_error,
                            snapshot.recovery_attempts,
                            snapshot.successful_recoveries,
                            snapshot.failed_recoveries,
                            snapshot.last_recovery_at,
                            snapshot.degradation_reason,
                            now_iso,
                        ),
                    )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeStatePersisted(
                            runtime_name=snapshot.runtime_name,
                            operational_state=snapshot.operational_state,
                            clean_shutdown=snapshot.clean_shutdown,
                        )
                    )
            except Exception as exc:
                logger.warning(
                    f"Failed to save persistent state for '{snapshot.runtime_name}': {exc}"
                )

    def load_snapshot(self, runtime_name: str) -> PersistentRuntimeSnapshot | None:
        """Loads the persisted PersistentRuntimeSnapshot for a given runtime."""
        snap: PersistentRuntimeSnapshot | None = None
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.execute(
                    "SELECT * FROM autonomy_persistent_state WHERE runtime_name = ?",
                    (runtime_name,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                snap = PersistentRuntimeSnapshot(
                    runtime_name=row["runtime_name"],
                    operational_state=row["operational_state"],
                    clean_shutdown=bool(row["clean_shutdown"]),
                    started_at=row["started_at"],
                    stopped_at=row["stopped_at"],
                    last_state_change_at=row["last_state_change_at"],
                    last_state_change_reason=row["last_state_change_reason"],
                    last_tick_at=row["last_tick_at"],
                    last_successful_tick_at=row["last_successful_tick_at"],
                    last_failed_tick_at=row["last_failed_tick_at"],
                    last_error=row["last_error"],
                    recovery_attempts=row["recovery_attempts"],
                    successful_recoveries=row["successful_recoveries"],
                    failed_recoveries=row["failed_recoveries"],
                    last_recovery_at=row["last_recovery_at"],
                    degradation_reason=row["degradation_reason"],
                    updated_at=row["updated_at"],
                )
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeStateRestored(
                            runtime_name=snap.runtime_name,
                            restored_state=snap.operational_state,
                            clean_shutdown=snap.clean_shutdown,
                        )
                    )
            except Exception as exc:
                logger.warning(f"Failed to load persistent state for '{runtime_name}': {exc}")
                return None
        return snap

    def mark_clean_shutdown(self, runtime_name: str, stopped_at: str | None = None) -> None:
        """Marks clean_shutdown = 1 and state = STOPPED upon graceful process termination."""
        with self._lock:
            try:
                now_iso = stopped_at or datetime.now(UTC).isoformat()
                conn = self._get_connection()
                with conn:
                    conn.execute(
                        """
                        UPDATE autonomy_persistent_state SET
                            operational_state = 'STOPPED',
                            clean_shutdown = 1,
                            stopped_at = ?,
                            updated_at = ?
                        WHERE runtime_name = ?
                        """,
                        (now_iso, now_iso, runtime_name),
                    )
            except Exception as exc:
                logger.warning(f"Failed to mark clean shutdown for '{runtime_name}': {exc}")

    def detect_unexpected_shutdown(self, runtime_name: str) -> bool:
        """Detects if the previous process crashed or exited ungracefully without clean shutdown."""
        with self._lock:
            snap = self.load_snapshot(runtime_name)
            if snap is None:
                return False
            if snap.clean_shutdown:
                return False
            if snap.operational_state in {"RUNNING", "STARTING", "DEGRADED", "RECOVERING"}:
                if self.event_bus:
                    now_iso = datetime.now(UTC).isoformat()
                    self.event_bus.publish(
                        RuntimeUnexpectedShutdownDetected(
                            runtime_name=runtime_name,
                            previous_state=snap.operational_state,
                            detected_at=now_iso,
                        )
                    )
                return True
            return False
