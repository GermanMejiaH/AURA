from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ..events import (
    AgentPlanCompleted,
    AgentPlanCreated,
    AgentReplanned,
    AgentSecurityAlert,
    Event,
    EventBus,
    ToolExecuted,
)
from ..logging import get_logger
from ..memory.store import SQLiteMemoryStore


class AgentExecutionHistoryStore:
    """Thread-safe store for append-only timeline of agentic execution events."""

    def __init__(
        self,
        db_path: str = "data/aura.db",
        store: SQLiteMemoryStore | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.store = store if store is not None else SQLiteMemoryStore(db_path=db_path)
        self._lock = self.store._lock
        self._init_table()

        if event_bus is not None:
            self.subscribe_to_bus(event_bus)

    def _init_table(self) -> None:
        logger = get_logger("AgentExecutionHistoryStore")
        with self._lock:
            try:
                conn = self.store._get_connection()
                with conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS agent_execution_history (
                            event_id TEXT PRIMARY KEY,
                            plan_id TEXT NOT NULL,
                            task_id TEXT,
                            event_type TEXT NOT NULL,
                            timestamp TEXT NOT NULL,
                            status TEXT,
                            tool_name TEXT,
                            replan_count INTEGER NOT NULL DEFAULT 0,
                            reason TEXT,
                            metadata_json TEXT NOT NULL DEFAULT '{}'
                        )
                        """
                    )
            except Exception as exc:
                logger.error(f"Failed to initialize agent_execution_history table: {exc}")

    def subscribe_to_bus(self, event_bus: EventBus) -> None:
        """Subscribes handler to EventBus events via wildcard subscription."""
        event_bus.subscribe("*", self.handle_event)

    def handle_event(self, event: Event) -> None:
        """Handler extracting plan history events from published EventBus events."""
        plan_id = getattr(event, "plan_id", "")
        if not plan_id and hasattr(event, "payload"):
            plan_id = event.payload.get("plan_id", "")

        if not plan_id:
            return

        evt_type = type(event).__name__
        task_id = getattr(event, "task_id", None)
        status = getattr(event, "evaluation_status", None) or getattr(event, "status", None)
        tool_name = getattr(event, "tool_name", None)
        replan_count = getattr(event, "replan_count", 0)
        reason = getattr(event, "reason", None) or getattr(event, "error", None)

        metadata: dict[str, Any] = {}
        if isinstance(event, AgentPlanCreated):
            metadata["goal_description"] = event.goal_description
            metadata["tasks_count"] = event.tasks_count
        elif isinstance(event, AgentPlanCompleted):
            status = (
                "SUCCESS"
                if event.completed
                else ("FAILED" if event.failed else "WAITING_CONFIRMATION")
            )
            metadata["steps_executed"] = event.steps_executed
            metadata["duration_ms"] = event.duration_ms
        elif isinstance(event, AgentReplanned):
            status = "REPLANNED"
            metadata["new_tasks_count"] = event.new_tasks_count
        elif isinstance(event, ToolExecuted):
            status = "SUCCESS" if event.success else "FAILED"
            metadata["execution_time_ms"] = event.execution_time_ms
        elif isinstance(event, AgentSecurityAlert):
            metadata["security_alert_type"] = event.event_type

        self.record_event(
            event_id=str(event.event_id),
            plan_id=plan_id,
            event_type=evt_type,
            timestamp=event.timestamp.isoformat(),
            task_id=task_id,
            status=status,
            tool_name=tool_name,
            replan_count=replan_count,
            reason=reason,
            metadata=metadata,
        )

    def record_event(
        self,
        event_id: str,
        plan_id: str,
        event_type: str,
        timestamp: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
        tool_name: str | None = None,
        replan_count: int = 0,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persists a single execution event record into SQLite atomically."""
        logger = get_logger("AgentExecutionHistoryStore")
        ts_str = timestamp or datetime.now(UTC).isoformat()
        meta_str = json.dumps(metadata or {})

        with self._lock:
            try:
                conn = self.store._get_connection()
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO agent_execution_history
                        (event_id, plan_id, task_id, event_type, timestamp, status, tool_name,
                         replan_count, reason, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            plan_id,
                            task_id,
                            event_type,
                            ts_str,
                            status,
                            tool_name,
                            replan_count,
                            reason,
                            meta_str,
                        ),
                    )
            except Exception as exc:
                logger.error(f"Failed to record history event '{event_id}': {exc}")

    def get_plan_history(self, plan_id: str) -> list[dict[str, Any]]:
        """Retrieves all append-only history records for a plan ordered chronologically."""
        logger = get_logger("AgentExecutionHistoryStore")
        with self._lock:
            try:
                conn = self.store._get_connection()
                cursor = conn.execute(
                    """
                    SELECT event_id, plan_id, task_id, event_type, timestamp, status, tool_name,
                           replan_count, reason, metadata_json
                    FROM agent_execution_history
                    WHERE plan_id = ?
                    ORDER BY timestamp ASC, event_id ASC
                    """,
                    (plan_id,),
                )
                rows = cursor.fetchall()
                records: list[dict[str, Any]] = []
                for r in rows:
                    try:
                        meta = json.loads(r["metadata_json"])
                    except Exception:
                        meta = {}
                    records.append(
                        {
                            "event_id": r["event_id"],
                            "plan_id": r["plan_id"],
                            "task_id": r["task_id"],
                            "event_type": r["event_type"],
                            "timestamp": r["timestamp"],
                            "status": r["status"],
                            "tool_name": r["tool_name"],
                            "replan_count": r["replan_count"],
                            "reason": r["reason"],
                            "metadata": meta,
                        }
                    )
            except Exception as exc:
                logger.error(f"Error reading history for plan '{plan_id}': {exc}")
                return []
            else:
                return records

    def get_plan_execution_tree(self, plan_id: str) -> dict[str, Any]:
        """Reconstructs the hierarchical execution trace and ascii tree representation."""
        records = self.get_plan_history(plan_id)
        if not records:
            return {
                "plan_id": plan_id,
                "status": "UNKNOWN",
                "timeline": [],
                "formatted_tree": f"Plan {plan_id}\n └─ (No history records)",
            }

        final_status = "UNKNOWN"
        tree_lines: list[str] = [f"Plan {plan_id}"]

        for rec in records:
            evt = rec["event_type"]
            task_str = f"Task {rec['task_id']}" if rec["task_id"] else "Task"
            tool_str = f" ({rec['tool_name']})" if rec["tool_name"] else ""

            if evt == "AgentPlanCreated":
                goal_desc = rec["metadata"].get("goal_description", "")
                if goal_desc:
                    tree_lines[0] = f"Plan {plan_id} (Goal: {goal_desc})"

            elif evt in ("ToolExecuted", "AgentStepEvaluated"):
                st = rec["status"] or "EXECUTED"
                tree_lines.append(f" ├─ {task_str} → {st}{tool_str}")

            elif evt == "AgentReplanRequested":
                err_reason = rec["reason"] or "Recoverable error"
                tree_lines.append(f" │    └─ REPLAN #{rec['replan_count']} (Reason: {err_reason})")

            elif evt == "AgentReplanned":
                new_cnt = rec["metadata"].get("new_tasks_count", 0)
                tree_lines.append(f" │         └─ REPLAN COMPLETED ({new_cnt} new tasks)")

            elif evt == "AgentConfirmationDenied":
                tree_lines.append(f" ├─ {task_str} → CANCELLED/DENIED{tool_str}")

            elif evt == "AgentPlanCompleted":
                final_status = rec["status"] or "COMPLETED"

        tree_lines.append(f" └─ Plan → {final_status}")
        formatted = "\n".join(tree_lines)

        return {
            "plan_id": plan_id,
            "status": final_status,
            "timeline": records,
            "formatted_tree": formatted,
        }
