from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ..autonomy.agent_models import AgentGoal, AgentPlan, AgentTask, TaskStatus
from ..logging import get_logger
from .store import SQLiteMemoryStore


class AgentPlanStore:
    """Thread-safe SQLite persistent store for AgentGoal, AgentPlan, and AgentTask records."""

    def __init__(
        self,
        db_path: str = "data/aura.db",
        store: SQLiteMemoryStore | None = None,
    ) -> None:
        self.store = store if store is not None else SQLiteMemoryStore(db_path=db_path)
        self._lock = self.store._lock

    def save_plan(self, plan: AgentPlan) -> None:
        """Atomically persists or updates an AgentPlan and all its associated AgentTasks."""
        logger = get_logger("AgentPlanStore")
        with self._lock:
            try:
                conn = self.store._get_connection()
                now_iso = datetime.now(UTC).isoformat()

                if plan.is_waiting_confirmation():
                    plan_status = TaskStatus.WAITING_CONFIRMATION.value
                elif plan.is_failed():
                    plan_status = TaskStatus.FAILED.value
                elif plan.is_completed():
                    plan_status = TaskStatus.SUCCESS.value
                elif any(t.status == TaskStatus.IN_PROGRESS for t in plan.tasks):
                    plan_status = TaskStatus.IN_PROGRESS.value
                else:
                    plan_status = plan.goal.status.value

                with conn:
                    conn.execute(
                        """
                        INSERT INTO agent_plans
                        (plan_id, goal_id, goal_description, status, replan_count, max_replans,
                         created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(plan_id) DO UPDATE SET
                            goal_id=excluded.goal_id,
                            goal_description=excluded.goal_description,
                            status=excluded.status,
                            replan_count=excluded.replan_count,
                            max_replans=excluded.max_replans,
                            updated_at=excluded.updated_at
                        """,
                        (
                            plan.plan_id,
                            plan.goal.goal_id,
                            plan.goal.description,
                            plan_status,
                            plan.replan_count,
                            plan.max_replans,
                            now_iso,
                            now_iso,
                        ),
                    )

                    conn.execute("DELETE FROM agent_tasks WHERE plan_id = ?", (plan.plan_id,))

                    for task in plan.get_ordered_tasks():
                        params_json = json.dumps(task.parameters)
                        res_json = json.dumps(task.result) if task.result is not None else None
                        conn.execute(
                            """
                            INSERT INTO agent_tasks
                            (task_id, plan_id, task_order, description, status, tool_name,
                             parameters_json, result_json, error)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                task.task_id,
                                plan.plan_id,
                                task.order,
                                task.description,
                                task.status.value,
                                task.tool_name,
                                params_json,
                                res_json,
                                task.error,
                            ),
                        )
                logger.debug(
                    f"Successfully saved AgentPlan '{plan.plan_id}' with {len(plan.tasks)} tasks."
                )
            except Exception as exc:
                logger.error(f"Failed to save AgentPlan '{plan.plan_id}': {exc}")
                raise

    def update_plan(self, plan: AgentPlan) -> None:
        """Updates plan status and task states after execution steps."""
        self.save_plan(plan)

    def get_plan(self, plan_id: str) -> AgentPlan | None:
        """Retrieves and reconstructs an AgentPlan domain model from persistent storage."""
        logger = get_logger("AgentPlanStore")
        with self._lock:
            try:
                conn = self.store._get_connection()
                cursor = conn.execute(
                    """
                    SELECT plan_id, goal_id, goal_description, status, replan_count,
                           max_replans, created_at, updated_at
                    FROM agent_plans WHERE plan_id = ?
                    """,
                    (plan_id,),
                )
                plan_row = cursor.fetchone()
                if plan_row is None:
                    return None

                task_cursor = conn.execute(
                    """
                    SELECT task_id, plan_id, task_order, description, status, tool_name,
                           parameters_json, result_json, error
                    FROM agent_tasks WHERE plan_id = ? ORDER BY task_order ASC
                    """,
                    (plan_id,),
                )
                task_rows = task_cursor.fetchall()

                goal = AgentGoal(
                    description=plan_row["goal_description"],
                    goal_id=plan_row["goal_id"],
                    status=TaskStatus(plan_row["status"]),
                )

                tasks: list[AgentTask] = []
                for r in task_rows:
                    try:
                        params = json.loads(r["parameters_json"])
                    except Exception:
                        params = {}

                    res_val: Any = None
                    if r["result_json"] is not None:
                        try:
                            res_val = json.loads(r["result_json"])
                        except Exception:
                            res_val = r["result_json"]

                    task_status_enum = TaskStatus(r["status"])

                    tasks.append(
                        AgentTask(
                            description=r["description"],
                            order=int(r["task_order"]),
                            task_id=r["task_id"],
                            status=task_status_enum,
                            tool_name=r["tool_name"],
                            parameters=params,
                            result=res_val,
                            error=r["error"],
                        )
                    )

                replan_count = plan_row["replan_count"] if "replan_count" in plan_row.keys() else 0
                max_replans = plan_row["max_replans"] if "max_replans" in plan_row.keys() else 2

                return AgentPlan(
                    goal=goal,
                    plan_id=plan_row["plan_id"],
                    tasks=tasks,
                    replan_count=int(replan_count),
                    max_replans=int(max_replans),
                )
            except Exception as exc:
                logger.error(f"Error reading AgentPlan '{plan_id}': {exc}")
                return None

    def delete_plan(self, plan_id: str) -> bool:
        """Deletes an AgentPlan and its associated tasks from persistent storage."""
        logger = get_logger("AgentPlanStore")
        with self._lock:
            try:
                conn = self.store._get_connection()
                with conn:
                    cur = conn.execute("DELETE FROM agent_plans WHERE plan_id = ?", (plan_id,))
                    deleted = cur.rowcount > 0
            except Exception as exc:
                logger.error(f"Error deleting AgentPlan '{plan_id}': {exc}")
                return False
            else:
                return deleted

    def list_active_plans(self) -> list[AgentPlan]:
        """Lists all active plans (status in PENDING, IN_PROGRESS, WAITING_CONFIRMATION)."""
        logger = get_logger("AgentPlanStore")
        with self._lock:
            try:
                conn = self.store._get_connection()
                cursor = conn.execute(
                    """
                    SELECT plan_id FROM agent_plans
                    WHERE status IN ('PENDING', 'IN_PROGRESS', 'WAITING_CONFIRMATION')
                    ORDER BY updated_at DESC
                    """
                )
                rows = cursor.fetchall()
                active_plans: list[AgentPlan] = []
                for r in rows:
                    plan = self.get_plan(r["plan_id"])
                    if plan is not None:
                        active_plans.append(plan)
            except Exception as exc:
                logger.error(f"Error listing active AgentPlans: {exc}")
                return []
            else:
                return active_plans
