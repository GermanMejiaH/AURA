from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from aura.autonomy.agent_models import AgentGoal, AgentPlan, AgentTask, TaskStatus
from aura.autonomy.executor import AgentExecutor
from aura.memory.plan_store import AgentPlanStore
from aura.memory.store import SQLiteMemoryStore
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.registry import ToolRegistry


class DangerousTool(BaseTool):
    metadata = ToolMetadata(
        name="dangerous_tool",
        description="Performs a high-risk operation",
        category="system",
        risk_level="destructive",
        requires_confirmation=True,
        parameters_schema={
            "type": "object",
            "required": ["target"],
            "properties": {"target": {"type": "string"}},
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output=f"Dangerous op executed on {kwargs.get('target')}")


class SafeTool(BaseTool):
    metadata = ToolMetadata(
        name="safe_tool",
        description="Safe query tool",
        category="general",
        risk_level="safe",
        parameters_schema={
            "type": "object",
            "properties": {"val": {"type": "string"}},
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output=f"Safe result: {kwargs.get('val')}")


@pytest.fixture
def tmp_db_path(tmp_path: Any) -> str:
    return str(tmp_path / "test_aura_plans.db")


def test_plan_store_table_creation(tmp_db_path: str) -> None:
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    _ = AgentPlanStore(store=store)

    conn = store._get_connection()
    sql_tables = (
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name IN ('agent_plans', 'agent_tasks')"
    )

    cursor = conn.execute(sql_tables)
    tables = [r["name"] for r in cursor.fetchall()]
    assert "agent_plans" in tables
    assert "agent_tasks" in tables


def test_save_and_get_plan(tmp_db_path: str) -> None:
    plan_store = AgentPlanStore(db_path=tmp_db_path)

    goal = AgentGoal(description="Test Goal")
    task1 = AgentTask(
        description="Step 1",
        order=1,
        tool_name="safe_tool",
        parameters={"val": "a"},
        status=TaskStatus.SUCCESS,
        result="Safe result: a",
    )
    task2 = AgentTask(
        description="Step 2",
        order=2,
        tool_name="safe_tool",
        parameters={"val": "b"},
        status=TaskStatus.PENDING,
    )
    plan = AgentPlan(goal=goal, tasks=[task1, task2])

    plan_store.save_plan(plan)
    reloaded = plan_store.get_plan(plan.plan_id)

    assert reloaded is not None
    assert reloaded.plan_id == plan.plan_id
    assert reloaded.goal.goal_id == goal.goal_id
    assert reloaded.goal.description == "Test Goal"
    assert len(reloaded.tasks) == 2

    assert reloaded.tasks[0].task_id == task1.task_id
    assert reloaded.tasks[0].order == 1
    assert reloaded.tasks[0].status == TaskStatus.SUCCESS
    assert reloaded.tasks[0].result == "Safe result: a"

    assert reloaded.tasks[1].task_id == task2.task_id
    assert reloaded.tasks[1].order == 2
    assert reloaded.tasks[1].status == TaskStatus.PENDING


def test_update_plan(tmp_db_path: str) -> None:
    plan_store = AgentPlanStore(db_path=tmp_db_path)

    goal = AgentGoal(description="Update Goal")
    task = AgentTask(description="Step 1", order=1, status=TaskStatus.PENDING)
    plan = AgentPlan(goal=goal, tasks=[task])

    plan_store.save_plan(plan)

    # Update task state
    task.status = TaskStatus.SUCCESS
    task.result = "Updated result"
    plan_store.update_plan(plan)

    reloaded = plan_store.get_plan(plan.plan_id)
    assert reloaded is not None
    assert reloaded.tasks[0].status == TaskStatus.SUCCESS
    assert reloaded.tasks[0].result == "Updated result"


def test_delete_plan(tmp_db_path: str) -> None:
    plan_store = AgentPlanStore(db_path=tmp_db_path)

    goal = AgentGoal(description="Delete Goal")
    task = AgentTask(description="Step 1", order=1)
    plan = AgentPlan(goal=goal, tasks=[task])

    plan_store.save_plan(plan)
    assert plan_store.get_plan(plan.plan_id) is not None

    deleted = plan_store.delete_plan(plan.plan_id)
    assert deleted is True
    assert plan_store.get_plan(plan.plan_id) is None


def test_cascade_delete_integrity(tmp_db_path: str) -> None:
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    plan_store = AgentPlanStore(store=store)

    goal = AgentGoal(description="Cascade Goal")
    task = AgentTask(description="Step 1", order=1)
    plan = AgentPlan(goal=goal, tasks=[task])

    plan_store.save_plan(plan)

    # Verify task exists in DB
    conn = store._get_connection()
    cur = conn.execute("SELECT COUNT(*) as cnt FROM agent_tasks WHERE plan_id = ?", (plan.plan_id,))
    assert cur.fetchone()["cnt"] == 1

    # Delete plan
    plan_store.delete_plan(plan.plan_id)

    # Verify task cascade deleted
    cur = conn.execute("SELECT COUNT(*) as cnt FROM agent_tasks WHERE plan_id = ?", (plan.plan_id,))
    assert cur.fetchone()["cnt"] == 0


def test_list_active_plans(tmp_db_path: str) -> None:
    plan_store = AgentPlanStore(db_path=tmp_db_path)

    p1 = AgentPlan(
        goal=AgentGoal(description="Active PENDING"),
        tasks=[AgentTask(description="T1", order=1, status=TaskStatus.PENDING)],
    )
    p2 = AgentPlan(
        goal=AgentGoal(description="Active WAITING"),
        tasks=[AgentTask(description="T2", order=1, status=TaskStatus.WAITING_CONFIRMATION)],
    )
    p3 = AgentPlan(
        goal=AgentGoal(description="Finished SUCCESS"),
        tasks=[AgentTask(description="T3", order=1, status=TaskStatus.SUCCESS)],
    )

    plan_store.save_plan(p1)
    plan_store.save_plan(p2)
    plan_store.save_plan(p3)

    active = plan_store.list_active_plans()
    active_ids = [p.plan_id for p in active]

    assert p1.plan_id in active_ids
    assert p2.plan_id in active_ids
    assert p3.plan_id not in active_ids


def test_rollback_on_persistence_error(tmp_db_path: str) -> None:
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    plan_store = AgentPlanStore(store=store)

    plan = AgentPlan(
        goal=AgentGoal(description="Rollback Goal"),
        tasks=[AgentTask(description="T1", order=1)],
    )
    plan_store.save_plan(plan)

    # Simulate an error by corrupting the store's inner transaction logic
    conn = store._get_connection()
    conn.execute("DROP TABLE agent_tasks")

    with pytest.raises(sqlite3.OperationalError):
        plan_store.save_plan(plan)


def test_corrupted_json_recovery(tmp_db_path: str) -> None:
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    plan_store = AgentPlanStore(store=store)

    plan = AgentPlan(
        goal=AgentGoal(description="Corrupted JSON Goal"),
        tasks=[AgentTask(description="T1", order=1, parameters={"a": 1})],
    )
    plan_store.save_plan(plan)

    # Corrupt JSON in database manually
    conn = store._get_connection()
    with conn:
        conn.execute(
            "UPDATE agent_tasks SET parameters_json = 'INVALID_JSON' WHERE plan_id = ?",
            (plan.plan_id,),
        )

    reloaded = plan_store.get_plan(plan.plan_id)
    assert reloaded is not None
    # Gracefully fallback to empty dict for corrupted parameters
    assert reloaded.tasks[0].parameters == {}


def test_empty_plan_tasks(tmp_db_path: str) -> None:
    plan_store = AgentPlanStore(db_path=tmp_db_path)
    plan = AgentPlan(goal=AgentGoal(description="Empty tasks plan"), tasks=[])

    plan_store.save_plan(plan)
    reloaded = plan_store.get_plan(plan.plan_id)

    assert reloaded is not None
    assert reloaded.tasks == []


def test_multiple_independent_plans(tmp_db_path: str) -> None:
    plan_store = AgentPlanStore(db_path=tmp_db_path)

    plans = [
        AgentPlan(
            goal=AgentGoal(description=f"Goal {i}"),
            tasks=[AgentTask(description=f"Task {i}", order=1)],
        )
        for i in range(5)
    ]

    for p in plans:
        plan_store.save_plan(p)

    for p in plans:
        reloaded = plan_store.get_plan(p.plan_id)
        assert reloaded is not None
        assert reloaded.goal.description == p.goal.description


def test_critical_waiting_confirmation_restart_flow(tmp_db_path: str) -> None:
    """CRITICAL TEST: Simulates creating a plan, pausing on WAITING_CONFIRMATION,

    persisting to SQLite, restarting AURA (closing store), reloading,
    authorizing, and resuming plan execution via AgentExecutor.
    """
    registry = ToolRegistry()
    registry.register(DangerousTool())
    registry.register(SafeTool())

    # 1. Create multi-step plan containing a dangerous tool
    goal = AgentGoal(description="Perform dangerous system operation")
    task1 = AgentTask(
        description="Run safe check",
        order=1,
        tool_name="safe_tool",
        parameters={"val": "pre_check"},
    )
    task2 = AgentTask(
        description="Run dangerous operation",
        order=2,
        tool_name="dangerous_tool",
        parameters={"target": "prod_server"},
    )
    plan = AgentPlan(goal=goal, tasks=[task1, task2])

    # 2. Execute plan up to WAITING_CONFIRMATION
    executor = AgentExecutor(registry=registry)
    res1 = executor.execute_plan(plan)

    assert res1.waiting_confirmation is True
    assert task1.status == TaskStatus.SUCCESS
    assert task2.status == TaskStatus.WAITING_CONFIRMATION

    # 3. Persist plan to SQLite
    store1 = SQLiteMemoryStore(db_path=tmp_db_path)
    plan_store1 = AgentPlanStore(store=store1)
    plan_store1.save_plan(plan)

    # 4. Simulate AURA restart: Close SQLite connection & destroy instances
    store1.close()
    del plan_store1
    del store1

    # 5. Simulate AURA startup: Open new SQLite connection and new AgentPlanStore
    store2 = SQLiteMemoryStore(db_path=tmp_db_path)
    plan_store2 = AgentPlanStore(store=store2)

    # 6. Retrieve plan from SQLite
    reloaded_plan = plan_store2.get_plan(plan.plan_id)
    assert reloaded_plan is not None
    assert reloaded_plan.plan_id == plan.plan_id
    assert reloaded_plan.goal.goal_id == goal.goal_id
    assert reloaded_plan.goal.description == goal.description
    assert len(reloaded_plan.tasks) == 2

    # Check task states
    t1 = reloaded_plan.tasks[0]
    t2 = reloaded_plan.tasks[1]
    assert t1.status == TaskStatus.SUCCESS
    assert t1.result == "Safe result: pre_check"
    assert t2.status == TaskStatus.WAITING_CONFIRMATION
    assert t2.parameters == {"target": "prod_server"}

    # 7. Authorize paused task and resume plan via AgentExecutor
    authorized = executor.authorize_task(reloaded_plan, t2.task_id)
    assert authorized is True

    # 8. Resume plan execution
    res2 = executor.resume_plan(reloaded_plan)

    assert res2.completed is True
    assert res2.failed is False
    assert reloaded_plan.is_completed() is True
    assert t2.status == TaskStatus.SUCCESS
    assert t2.result == "Dangerous op executed on prod_server"

    # 9. Update final plan state in SQLite
    plan_store2.update_plan(reloaded_plan)
    final_reloaded = plan_store2.get_plan(plan.plan_id)

    assert final_reloaded is not None
    assert final_reloaded.is_completed() is True
    store2.close()
