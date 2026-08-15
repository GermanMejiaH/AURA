from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

from aura.logging import get_logger
from aura.memory.store import SQLiteMemoryStore

from .models import ScheduleStatus, ScheduleType, TemporalSchedule

logger = get_logger("ScheduleStore")


class ScheduleStore:
    """Persistence store for TemporalSchedule domain models using SQLite."""

    def __init__(
        self,
        db_path: str = "data/aura.db",
        store: SQLiteMemoryStore | None = None,
    ) -> None:
        if store is not None:
            self._memory_store = store
            self.db_path = store.db_path
        else:
            self._memory_store = SQLiteMemoryStore(db_path=db_path)
            self.db_path = db_path

        self._lock: threading.RLock = self._memory_store._lock
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return self._memory_store._get_connection()

    def _init_db(self) -> None:
        with self._lock:
            try:
                from aura.cognition.goals.store import GoalStore

                GoalStore(store=self._memory_store)

                conn = self._get_connection()
                with conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS temporal_schedules (
                            schedule_id TEXT PRIMARY KEY,
                            goal_id TEXT NOT NULL,
                            schedule_type TEXT NOT NULL,
                            status TEXT NOT NULL,
                            expression TEXT NOT NULL DEFAULT '',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            last_run_at TEXT,
                            next_run_at TEXT,
                            max_iterations INTEGER,
                            iterations_count INTEGER NOT NULL DEFAULT 0,
                            metadata_json TEXT NOT NULL DEFAULT '{}',
                            FOREIGN KEY (goal_id)
                            REFERENCES persistent_goals(goal_id) ON DELETE CASCADE
                        )
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_schedules_status
                        ON temporal_schedules(status)
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_schedules_type
                        ON temporal_schedules(schedule_type)
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_schedules_goal
                        ON temporal_schedules(goal_id)
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_schedules_next_run
                        ON temporal_schedules(next_run_at)
                        """
                    )
            except Exception as exc:
                logger.error(
                    f"Failed to initialize temporal_schedules table in '{self.db_path}': {exc}"
                )

    def save_schedule(self, schedule: TemporalSchedule) -> None:
        """Saves or updates a TemporalSchedule in the SQLite store."""
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO temporal_schedules (
                        schedule_id, goal_id, schedule_type, status, expression,
                        created_at, updated_at, last_run_at, next_run_at,
                        max_iterations, iterations_count, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        schedule.schedule_id,
                        schedule.goal_id,
                        schedule.schedule_type.value
                        if isinstance(schedule.schedule_type, ScheduleType)
                        else str(schedule.schedule_type),
                        schedule.status.value
                        if isinstance(schedule.status, ScheduleStatus)
                        else str(schedule.status),
                        schedule.expression,
                        schedule.created_at,
                        schedule.updated_at,
                        schedule.last_run_at,
                        schedule.next_run_at,
                        schedule.max_iterations,
                        schedule.iterations_count,
                        json.dumps(schedule.metadata),
                    ),
                )

    def get_schedule(self, schedule_id: str) -> TemporalSchedule | None:
        """Retrieves a TemporalSchedule by ID."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM temporal_schedules WHERE schedule_id = ?", (schedule_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_schedule(row)

    def list_schedules(
        self,
        goal_id: str | None = None,
        status: ScheduleStatus | str | None = None,
        schedule_type: ScheduleType | str | None = None,
    ) -> list[TemporalSchedule]:
        """Lists TemporalSchedules with optional filters."""
        query = "SELECT * FROM temporal_schedules WHERE 1=1"
        params: list[Any] = []

        if goal_id is not None:
            query += " AND goal_id = ?"
            params.append(goal_id)

        if status is not None:
            status_val = status.value if isinstance(status, ScheduleStatus) else str(status)
            query += " AND status = ?"
            params.append(status_val)

        if schedule_type is not None:
            type_val = (
                schedule_type.value
                if isinstance(schedule_type, ScheduleType)
                else str(schedule_type)
            )
            query += " AND schedule_type = ?"
            params.append(type_val)

        query += " ORDER BY created_at ASC"

        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_schedule(r) for r in rows]

    def list_eligible_schedules(self, at_timestamp: str | None = None) -> list[TemporalSchedule]:
        """Lists active schedules eligible for execution at the given ISO timestamp."""
        all_active = self.list_schedules(status=ScheduleStatus.ACTIVE)
        target_time = at_timestamp or datetime.now(UTC).isoformat()
        return [s for s in all_active if s.is_eligible(at_timestamp=target_time)]

    def delete_schedule(self, schedule_id: str) -> bool:
        """Physically deletes a TemporalSchedule by ID."""
        with self._lock:
            conn = self._get_connection()
            with conn:
                cursor = conn.execute(
                    "DELETE FROM temporal_schedules WHERE schedule_id = ?", (schedule_id,)
                )
                return cursor.rowcount > 0

    def _row_to_schedule(self, row: sqlite3.Row) -> TemporalSchedule:
        try:
            meta = json.loads(row["metadata_json"])
        except Exception:
            meta = {}

        try:
            stype = ScheduleType(row["schedule_type"])
        except Exception:
            stype = ScheduleType.ONE_SHOT

        try:
            status = ScheduleStatus(row["status"])
        except Exception:
            status = ScheduleStatus.ACTIVE

        return TemporalSchedule(
            schedule_id=row["schedule_id"],
            goal_id=row["goal_id"],
            schedule_type=stype,
            status=status,
            expression=row["expression"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_run_at=row["last_run_at"],
            next_run_at=row["next_run_at"],
            max_iterations=row["max_iterations"],
            iterations_count=row["iterations_count"],
            metadata=meta,
        )
