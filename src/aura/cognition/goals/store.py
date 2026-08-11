from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from aura.cognition.deliberation.models import RiskLevel
from aura.logging import get_logger
from aura.memory.store import SQLiteMemoryStore

from .models import (
    GoalContextRef,
    GoalPriority,
    GoalProgress,
    GoalStatus,
    PersistentGoal,
)

logger = get_logger("GoalStore")


class GoalStore:
    """Persistence store for PersistentGoal domain models using SQLite."""

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
                conn = self._get_connection()
                with conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS persistent_goals (
                            goal_id TEXT PRIMARY KEY,
                            description TEXT NOT NULL,
                            priority TEXT NOT NULL,
                            status TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            success_criteria_json TEXT NOT NULL DEFAULT '[]',
                            constraints_json TEXT NOT NULL DEFAULT '[]',
                            context_json TEXT NOT NULL DEFAULT '{}',
                            progress_json TEXT NOT NULL DEFAULT '{}',
                            parent_goal_id TEXT,
                            risk_tolerance TEXT NOT NULL DEFAULT 'MEDIUM',
                            FOREIGN KEY (parent_goal_id)
                            REFERENCES persistent_goals(goal_id) ON DELETE SET NULL
                        )
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_persistent_goals_status
                        ON persistent_goals(status)
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_persistent_goals_priority
                        ON persistent_goals(priority)
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_persistent_goals_parent
                        ON persistent_goals(parent_goal_id)
                        """
                    )
            except Exception as exc:
                logger.error(
                    f"Failed to initialize persistent_goals table in '{self.db_path}': {exc}"
                )

    def save_goal(self, goal: PersistentGoal) -> None:
        """Saves or updates a PersistentGoal in the SQLite store."""
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO persistent_goals (
                        goal_id, description, priority, status, created_at, updated_at,
                        success_criteria_json, constraints_json, context_json,
                        progress_json, parent_goal_id, risk_tolerance
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        goal.goal_id,
                        goal.description,
                        goal.priority.value
                        if isinstance(goal.priority, GoalPriority)
                        else str(goal.priority),
                        goal.status.value
                        if isinstance(goal.status, GoalStatus)
                        else str(goal.status),
                        goal.created_at,
                        goal.updated_at,
                        json.dumps(goal.success_criteria),
                        json.dumps(goal.constraints),
                        json.dumps(
                            {
                                "location": goal.context.location,
                                "entities": goal.context.entities,
                                "tags": goal.context.tags,
                                "metadata": goal.context.metadata,
                            }
                        ),
                        json.dumps(
                            {
                                "completion_percentage": goal.progress.completion_percentage,
                                "milestones_completed": goal.progress.milestones_completed,
                                "last_updated_at": goal.progress.last_updated_at,
                                "notes": goal.progress.notes,
                            }
                        ),
                        goal.parent_goal_id,
                        goal.risk_tolerance.value
                        if isinstance(goal.risk_tolerance, RiskLevel)
                        else str(goal.risk_tolerance),
                    ),
                )

    def get_goal(self, goal_id: str) -> PersistentGoal | None:
        """Retrieves a PersistentGoal by its ID."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM persistent_goals WHERE goal_id = ?", (goal_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_persistent_goal(row)

    def list_goals(
        self,
        status: GoalStatus | str | None = None,
        priority: GoalPriority | str | None = None,
        parent_goal_id: str | None = None,
    ) -> list[PersistentGoal]:
        """Lists PersistentGoals with optional status, priority, or parent filters."""
        query = "SELECT * FROM persistent_goals WHERE 1=1"
        params: list[Any] = []

        if status is not None:
            status_val = status.value if isinstance(status, GoalStatus) else str(status)
            query += " AND status = ?"
            params.append(status_val)

        if priority is not None:
            priority_val = priority.value if isinstance(priority, GoalPriority) else str(priority)
            query += " AND priority = ?"
            params.append(priority_val)

        if parent_goal_id is not None:
            query += " AND parent_goal_id = ?"
            params.append(parent_goal_id)

        query += " ORDER BY created_at ASC"

        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_persistent_goal(r) for r in rows]

    def delete_goal(self, goal_id: str) -> bool:
        """Physically deletes a PersistentGoal by ID from the database."""
        with self._lock:
            conn = self._get_connection()
            with conn:
                cursor = conn.execute("DELETE FROM persistent_goals WHERE goal_id = ?", (goal_id,))
                return cursor.rowcount > 0

    def _row_to_persistent_goal(self, row: sqlite3.Row) -> PersistentGoal:
        try:
            criteria = json.loads(row["success_criteria_json"])
        except Exception:
            criteria = []

        try:
            constraints = json.loads(row["constraints_json"])
        except Exception:
            constraints = []

        try:
            ctx_data = json.loads(row["context_json"])
            context = GoalContextRef(
                location=ctx_data.get("location"),
                entities=ctx_data.get("entities", []),
                tags=ctx_data.get("tags", []),
                metadata=ctx_data.get("metadata", {}),
            )
        except Exception:
            context = GoalContextRef()

        try:
            prog_data = json.loads(row["progress_json"])
            progress = GoalProgress(
                completion_percentage=prog_data.get("completion_percentage", 0.0),
                milestones_completed=prog_data.get("milestones_completed", []),
                last_updated_at=prog_data.get("last_updated_at", row["updated_at"]),
                notes=prog_data.get("notes", ""),
            )
        except Exception:
            progress = GoalProgress()

        try:
            priority = GoalPriority(row["priority"])
        except Exception:
            priority = GoalPriority.MEDIUM

        try:
            status = GoalStatus(row["status"])
        except Exception:
            status = GoalStatus.PENDING

        try:
            risk_tolerance = RiskLevel(row["risk_tolerance"])
        except Exception:
            risk_tolerance = RiskLevel.MEDIUM

        return PersistentGoal(
            goal_id=row["goal_id"],
            description=row["description"],
            priority=priority,
            status=status,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            success_criteria=criteria,
            constraints=constraints,
            context=context,
            progress=progress,
            parent_goal_id=row["parent_goal_id"],
            risk_tolerance=risk_tolerance,
        )
