"""Stage 23 — Persistent Proactive Task Store.

Thread-safe SQLite persistent store implementation for proactive tasks,
execution logs, and grounded result notifications using SQLiteMemoryStore.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

from aura.logging import get_logger
from aura.memory.store import SQLiteMemoryStore

from .contract import (
    ActionProposal,
    ProactiveNotification,
    ProactiveTask,
    ProactiveTaskStatus,
    TriggerDefinition,
    TriggerType,
)

logger = get_logger("ProactiveTaskStore")


class ProactiveTaskStore:
    """Thread-safe SQLite store for persisting proactive tasks and notifications."""

    def __init__(self, store: SQLiteMemoryStore | None = None) -> None:
        self.store = store or SQLiteMemoryStore(db_path=":memory:")
        self._lock = threading.RLock()

    def _get_conn(self) -> sqlite3.Connection:
        return self.store._get_connection()

    def save_task(self, task: ProactiveTask) -> None:
        """Saves or updates a ProactiveTask record in SQLite."""
        with self._lock:
            conn = self._get_conn()
            now_iso = datetime.now(UTC).isoformat()
            trigger_json = json.dumps(task.trigger_definition.to_dict())
            action_json = json.dumps(task.action_proposal.to_dict())
            meta_json = json.dumps(task.metadata or {})

            with conn:
                conn.execute(
                    """
                    INSERT INTO proactive_tasks (
                        task_id, conversation_id, creation_turn_id, trigger_type,
                        trigger_definition_json, action_proposal_json, status,
                        created_at, updated_at, next_evaluation_at, last_evaluation_at,
                        execution_count, max_executions, expires_at, correlation_id,
                        operation_id, last_execution_id, last_outcome_id, cancellation_reason,
                        metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        status = excluded.status,
                        updated_at = excluded.updated_at,
                        next_evaluation_at = excluded.next_evaluation_at,
                        last_evaluation_at = excluded.last_evaluation_at,
                        execution_count = excluded.execution_count,
                        max_executions = excluded.max_executions,
                        operation_id = excluded.operation_id,
                        last_execution_id = excluded.last_execution_id,
                        last_outcome_id = excluded.last_outcome_id,
                        cancellation_reason = excluded.cancellation_reason,
                        metadata_json = excluded.metadata_json;
                    """,
                    (
                        task.task_id,
                        task.conversation_id,
                        task.creation_turn_id,
                        task.trigger_type.value,
                        trigger_json,
                        action_json,
                        task.status.value,
                        task.created_at,
                        now_iso,
                        task.next_evaluation_at,
                        task.last_evaluation_at,
                        task.execution_count,
                        task.max_executions,
                        task.expires_at,
                        task.correlation_id,
                        task.operation_id,
                        task.last_execution_id,
                        task.last_outcome_id,
                        task.cancellation_reason,
                        meta_json,
                    ),
                )

    def get_task(self, task_id: str) -> ProactiveTask | None:
        """Retrieves a ProactiveTask by ID."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT task_id, conversation_id, creation_turn_id, trigger_type,
                       trigger_definition_json, action_proposal_json, status,
                       created_at, updated_at, next_evaluation_at, last_evaluation_at,
                       execution_count, max_executions, expires_at, correlation_id,
                       operation_id, last_execution_id, last_outcome_id, cancellation_reason,
                       metadata_json
                FROM proactive_tasks
                WHERE task_id = ?;
                """,
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def list_tasks(
        self,
        conversation_id: str | None = None,
        status: ProactiveTaskStatus | str | None = None,
        limit: int = 100,
    ) -> list[ProactiveTask]:
        """Lists tasks filtered by conversation_id or status."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            query = """
                SELECT task_id, conversation_id, creation_turn_id, trigger_type,
                       trigger_definition_json, action_proposal_json, status,
                       created_at, updated_at, next_evaluation_at, last_evaluation_at,
                       execution_count, max_executions, expires_at, correlation_id,
                       operation_id, last_execution_id, last_outcome_id, cancellation_reason,
                       metadata_json
                FROM proactive_tasks
            """
            conditions: list[str] = []
            params: list[Any] = []

            if conversation_id:
                conditions.append("conversation_id = ?")
                params.append(conversation_id)
            if status:
                st_val = status.value if hasattr(status, "value") else str(status)
                conditions.append("status = ?")
                params.append(st_val)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY created_at DESC LIMIT ?;"
            params.append(limit)

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [self._row_to_task(r) for r in rows]

    def list_active_tasks(self) -> list[ProactiveTask]:
        """Lists all tasks currently pending or active for trigger evaluation."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            active_states = (
                ProactiveTaskStatus.PENDING.value,
                ProactiveTaskStatus.ACTIVE.value,
                ProactiveTaskStatus.TRIGGERED.value,
            )
            cursor.execute(
                """
                SELECT task_id, conversation_id, creation_turn_id, trigger_type,
                       trigger_definition_json, action_proposal_json, status,
                       created_at, updated_at, next_evaluation_at, last_evaluation_at,
                       execution_count, max_executions, expires_at, correlation_id,
                       operation_id, last_execution_id, last_outcome_id, cancellation_reason,
                       metadata_json
                FROM proactive_tasks
                WHERE status IN (?, ?, ?)
                ORDER BY created_at ASC;
                """,
                active_states,
            )
            rows = cursor.fetchall()
            return [self._row_to_task(r) for r in rows]

    def claim_task_for_execution(self, task_id: str) -> bool:
        """Atomically transitions task status to EXECUTING.

        Returns True if row was updated (task claimed), False if already claimed or finished.
        Guarantees idempotency under concurrent evaluations.
        """
        with self._lock:
            conn = self._get_conn()
            now_iso = datetime.now(UTC).isoformat()
            valid_claim_states = (
                ProactiveTaskStatus.PENDING.value,
                ProactiveTaskStatus.ACTIVE.value,
                ProactiveTaskStatus.TRIGGERED.value,
            )
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE proactive_tasks
                    SET status = ?, updated_at = ?
                    WHERE task_id = ? AND status IN (?, ?, ?);
                    """,
                    (
                        ProactiveTaskStatus.EXECUTING.value,
                        now_iso,
                        task_id,
                        *valid_claim_states,
                    ),
                )
                return cursor.rowcount == 1

    def update_task_status(
        self,
        task_id: str,
        status: ProactiveTaskStatus,
        operation_id: str | None = None,
        cancellation_reason: str | None = None,
        increment_execution_count: bool = False,
    ) -> None:
        """Updates task status, operation correlation, and execution counts."""
        with self._lock:
            conn = self._get_conn()
            now_iso = datetime.now(UTC).isoformat()
            with conn:
                if increment_execution_count:
                    conn.execute(
                        """
                        UPDATE proactive_tasks
                        SET status = ?, updated_at = ?, operation_id = COALESCE(?, operation_id),
                            cancellation_reason = COALESCE(?, cancellation_reason),
                            execution_count = execution_count + 1,
                            last_evaluation_at = ?
                        WHERE task_id = ?;
                        """,
                        (
                            status.value,
                            now_iso,
                            operation_id,
                            cancellation_reason,
                            now_iso,
                            task_id,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE proactive_tasks
                        SET status = ?, updated_at = ?, operation_id = COALESCE(?, operation_id),
                            cancellation_reason = COALESCE(?, cancellation_reason),
                            last_evaluation_at = ?
                        WHERE task_id = ?;
                        """,
                        (
                            status.value,
                            now_iso,
                            operation_id,
                            cancellation_reason,
                            now_iso,
                            task_id,
                        ),
                    )

    def cancel_task(self, task_id: str, reason: str = "Manual cancellation") -> bool:
        """Cancels a pending or active task."""
        with self._lock:
            conn = self._get_conn()
            now_iso = datetime.now(UTC).isoformat()
            cancellable_states = (
                ProactiveTaskStatus.PENDING.value,
                ProactiveTaskStatus.ACTIVE.value,
                ProactiveTaskStatus.TRIGGERED.value,
                ProactiveTaskStatus.EXECUTING.value,
            )
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE proactive_tasks
                    SET status = ?, cancellation_reason = ?, updated_at = ?
                    WHERE task_id = ? AND status IN (?, ?, ?, ?);
                    """,
                    (
                        ProactiveTaskStatus.CANCELLED.value,
                        reason,
                        now_iso,
                        task_id,
                        *cancellable_states,
                    ),
                )
                return cursor.rowcount == 1

    def cancel_all_tasks(
        self, conversation_id: str, reason: str = "Batch user cancellation"
    ) -> int:
        """Cancels all active or pending tasks for a conversation."""
        with self._lock:
            conn = self._get_conn()
            now_iso = datetime.now(UTC).isoformat()
            cancellable_states = (
                ProactiveTaskStatus.PENDING.value,
                ProactiveTaskStatus.ACTIVE.value,
                ProactiveTaskStatus.TRIGGERED.value,
            )
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE proactive_tasks
                    SET status = ?, cancellation_reason = ?, updated_at = ?
                    WHERE conversation_id = ? AND status IN (?, ?, ?);
                    """,
                    (
                        ProactiveTaskStatus.CANCELLED.value,
                        reason,
                        now_iso,
                        conversation_id,
                        *cancellable_states,
                    ),
                )
                return cursor.rowcount

    def save_notification(self, notification: ProactiveNotification) -> None:
        """Persists a grounded result notification in SQLite."""
        with self._lock:
            conn = self._get_conn()
            meta_json = json.dumps(notification.metadata or {})
            with conn:
                conn.execute(
                    """
                    INSERT INTO proactive_notifications (
                        notification_id, task_id, conversation_id, title, content,
                        success, created_at, delivered, operation_id, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(notification_id) DO UPDATE SET
                        delivered = excluded.delivered,
                        content = excluded.content;
                    """,
                    (
                        notification.notification_id,
                        notification.task_id,
                        notification.conversation_id,
                        notification.title,
                        notification.content,
                        1 if notification.success else 0,
                        notification.created_at,
                        1 if notification.delivered else 0,
                        notification.operation_id,
                        meta_json,
                    ),
                )

    def list_notifications(
        self,
        conversation_id: str | None = None,
        undelivered_only: bool = False,
        limit: int = 50,
    ) -> list[ProactiveNotification]:
        """Lists result notifications filtered by conversation_id and delivery state."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            query = """
                SELECT notification_id, task_id, conversation_id, title, content,
                       success, created_at, delivered, operation_id, metadata_json
                FROM proactive_notifications
            """
            conditions: list[str] = []
            params: list[Any] = []

            if conversation_id:
                conditions.append("conversation_id = ?")
                params.append(conversation_id)
            if undelivered_only:
                conditions.append("delivered = 0")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY created_at DESC LIMIT ?;"
            params.append(limit)

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [
                ProactiveNotification(
                    notification_id=r[0],
                    task_id=r[1],
                    conversation_id=r[2],
                    title=r[3],
                    content=r[4],
                    success=bool(r[5]),
                    created_at=r[6],
                    delivered=bool(r[7]),
                    operation_id=r[8],
                    metadata=json.loads(r[9]) if r[9] else {},
                )
                for r in rows
            ]

    def mark_notifications_delivered(self, notification_ids: list[str]) -> None:
        """Marks notifications as delivered."""
        if not notification_ids:
            return
        with self._lock:
            conn = self._get_conn()
            placeholders = ",".join("?" for _ in notification_ids)
            query = (
                "UPDATE proactive_notifications SET delivered = 1 "
                f"WHERE notification_id IN ({placeholders});"
            )
            with conn:
                conn.execute(query, tuple(notification_ids))

    def _row_to_task(self, row: Any) -> ProactiveTask:
        t_def_dict = json.loads(row[4]) if row[4] else {}
        a_prop_dict = json.loads(row[5]) if row[5] else {}
        meta_dict = json.loads(row[19]) if row[19] else {}

        return ProactiveTask(
            task_id=row[0],
            conversation_id=row[1],
            creation_turn_id=row[2],
            trigger_type=TriggerType(row[3]),
            trigger_definition=TriggerDefinition.from_dict(t_def_dict),
            action_proposal=ActionProposal.from_dict(a_prop_dict),
            status=ProactiveTaskStatus(row[6]),
            created_at=row[7],
            updated_at=row[8],
            next_evaluation_at=row[9],
            last_evaluation_at=row[10],
            execution_count=row[11],
            max_executions=row[12],
            expires_at=row[13],
            correlation_id=row[14],
            operation_id=row[15],
            last_execution_id=row[16],
            last_outcome_id=row[17],
            cancellation_reason=row[18],
            metadata=meta_dict,
        )
