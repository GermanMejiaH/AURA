from __future__ import annotations

import inspect
from typing import Any

import pytest

from aura.autonomy.executor import AgentExecutor
from aura.autonomy.history import AgentExecutionHistoryStore
from aura.autonomy.metrics import AgentMetricsCollector
from aura.autonomy.planner import AgentPlanner
from aura.cognition.provider import LLMProvider, LLMResponse
from aura.events import (
    AgentConfirmationDenied,
    AgentConfirmationGranted,
    AgentPlanCompleted,
    AgentPlanCreated,
    AgentReplanFailed,
    AgentReplanned,
    AgentReplanRequested,
    AgentSecurityAlert,
    EventBus,
    ToolConfirmationRequired,
    ToolExecuted,
    ToolFailed,
)
from aura.memory.store import SQLiteMemoryStore
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.registry import ToolRegistry


class DummyLLM(LLMProvider):
    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        return LLMResponse(content="Response")

    def structured_reason(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "tasks": [
                {
                    "description": "Calc task",
                    "order": 1,
                    "tool_name": "calc",
                    "parameters": {"expr": "1+1"},
                }
            ]
        }


class DummyTool(BaseTool):
    metadata = ToolMetadata(
        name="calc",
        description="Calculadora",
        category="math",
        parameters_schema={
            "type": "object",
            "required": ["expr"],
            "properties": {"expr": {"type": "string"}},
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output="2")


@pytest.fixture
def tmp_db_path(tmp_path: Any) -> str:
    return str(tmp_path / "stage5_observability.db")


# -------------------------------------------------------------------
# METRICS TESTS (1 - 14)
# -------------------------------------------------------------------


def test_metrics_01_plan_created() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(AgentPlanCreated(plan_id="p1", goal_description="Goal", tasks_count=2))
    summary = collector.get_summary()
    assert summary.plans_created == 1


def test_metrics_02_plan_completed() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(AgentPlanCompleted(plan_id="p1", completed=True, duration_ms=100.0))
    summary = collector.get_summary()
    assert summary.plans_completed == 1
    assert summary.average_plan_execution_time == 100.0


def test_metrics_03_plan_failed() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(AgentPlanCompleted(plan_id="p1", completed=False, failed=True))
    summary = collector.get_summary()
    assert summary.plans_failed == 1


def test_metrics_04_plan_waiting_confirmation() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(
        AgentPlanCompleted(plan_id="p1", completed=False, failed=False, waiting_confirmation=True)
    )
    summary = collector.get_summary()
    assert summary.plans_waiting_confirmation == 1


def test_metrics_05_task_succeeded() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(ToolExecuted(tool_name="calc", success=True, execution_time_ms=50.0))
    summary = collector.get_summary()
    assert summary.tasks_executed == 1
    assert summary.tasks_succeeded == 1
    assert summary.tool_executions["calc"] == 1


def test_metrics_06_task_failed() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(ToolExecuted(tool_name="calc", success=False, execution_time_ms=10.0))
    summary = collector.get_summary()
    assert summary.tasks_executed == 1
    assert summary.tasks_failed == 1
    assert summary.tool_errors["calc"] == 1


def test_metrics_07_replan_requested() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(AgentReplanRequested(plan_id="p1", task_id="t1", replan_count=1))
    summary = collector.get_summary()
    assert summary.replans_requested == 1


def test_metrics_08_replan_succeeded() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(AgentReplanned(plan_id="p1", task_id="t1", replan_count=1))
    summary = collector.get_summary()
    assert summary.replans_succeeded == 1


def test_metrics_09_replan_failed() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(AgentReplanFailed(plan_id="p1", task_id="t1", replan_count=1, reason="Failed"))
    summary = collector.get_summary()
    assert summary.replans_failed == 1


def test_metrics_10_tool_errors_grouped_by_name() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(ToolFailed(tool_name="flaky", error="error 1"))
    bus.publish(ToolFailed(tool_name="flaky", error="error 2"))
    bus.publish(ToolFailed(tool_name="calc", error="error 3"))
    summary = collector.get_summary()
    assert summary.tool_errors["flaky"] == 2
    assert summary.tool_errors["calc"] == 1


def test_metrics_11_confirmation_granted() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(ToolConfirmationRequired(tool_name="danger"))
    bus.publish(AgentConfirmationGranted(plan_id="p1", task_id="t1", tool_name="danger"))
    summary = collector.get_summary()
    assert summary.authorization_requests == 1
    assert summary.confirmations_granted == 1


def test_metrics_12_confirmation_denied() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(AgentConfirmationDenied(plan_id="p1", task_id="t1", tool_name="danger"))
    summary = collector.get_summary()
    assert summary.confirmations_denied == 1


def test_metrics_13_replan_blocked_by_limit() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(
        AgentSecurityAlert(
            event_type="replan_blocked_limit", tool_name="calc", reason="Limit reached"
        )
    )
    summary = collector.get_summary()
    assert summary.replans_blocked_by_limit == 1


def test_metrics_14_replan_blocked_by_loop() -> None:
    bus = EventBus()
    collector = AgentMetricsCollector(event_bus=bus)
    bus.publish(
        AgentSecurityAlert(
            event_type="replan_blocked_loop", tool_name="calc", reason="Loop blocked"
        )
    )
    summary = collector.get_summary()
    assert summary.replans_blocked_by_loop == 1


# -------------------------------------------------------------------
# HISTORY TESTS (15 - 21)
# -------------------------------------------------------------------


def test_history_15_event_persistence(tmp_db_path: str) -> None:
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    history = AgentExecutionHistoryStore(store=store)
    history.record_event(
        event_id="e1",
        plan_id="plan_100",
        event_type="AgentPlanCreated",
        task_id="t1",
        status="PENDING",
    )
    records = history.get_plan_history("plan_100")
    assert len(records) == 1
    assert records[0]["event_id"] == "e1"
    assert records[0]["event_type"] == "AgentPlanCreated"


def test_history_16_recovery_after_sqlite_reopen(tmp_db_path: str) -> None:
    store1 = SQLiteMemoryStore(db_path=tmp_db_path)
    h1 = AgentExecutionHistoryStore(store=store1)
    h1.record_event(
        event_id="e_persist",
        plan_id="plan_reopen",
        event_type="AgentPlanCreated",
    )
    store1.close()

    store2 = SQLiteMemoryStore(db_path=tmp_db_path)
    h2 = AgentExecutionHistoryStore(store=store2)
    records = h2.get_plan_history("plan_reopen")
    assert len(records) == 1
    assert records[0]["event_id"] == "e_persist"


def test_history_17_chronological_ordering(tmp_db_path: str) -> None:
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    history = AgentExecutionHistoryStore(store=store)
    history.record_event(
        event_id="e1",
        plan_id="p_chrono",
        event_type="AgentPlanCreated",
        timestamp="2026-08-10T10:00:00Z",
    )
    history.record_event(
        event_id="e2",
        plan_id="p_chrono",
        event_type="ToolExecuted",
        timestamp="2026-08-10T10:01:00Z",
    )
    history.record_event(
        event_id="e3",
        plan_id="p_chrono",
        event_type="AgentPlanCompleted",
        timestamp="2026-08-10T10:02:00Z",
    )

    recs = history.get_plan_history("p_chrono")
    assert [r["event_id"] for r in recs] == ["e1", "e2", "e3"]


def test_history_18_linear_execution_tree_reconstruction(tmp_db_path: str) -> None:
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    history = AgentExecutionHistoryStore(store=store)
    history.record_event(
        event_id="e1",
        plan_id="p_lin",
        event_type="AgentPlanCreated",
        metadata={"goal_description": "Linear goal"},
    )
    history.record_event(
        event_id="e2",
        plan_id="p_lin",
        event_type="ToolExecuted",
        task_id="t1",
        tool_name="calc",
        status="SUCCESS",
    )
    history.record_event(
        event_id="e3", plan_id="p_lin", event_type="AgentPlanCompleted", status="SUCCESS"
    )

    tree = history.get_plan_execution_tree("p_lin")
    assert tree["status"] == "SUCCESS"
    assert "Linear goal" in tree["formatted_tree"]
    assert "Task t1 → SUCCESS (calc)" in tree["formatted_tree"]


def test_history_19_replanned_execution_tree_reconstruction(tmp_db_path: str) -> None:
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    history = AgentExecutionHistoryStore(store=store)
    history.record_event(event_id="e1", plan_id="p_replan", event_type="AgentPlanCreated")
    history.record_event(
        event_id="e2",
        plan_id="p_replan",
        event_type="ToolExecuted",
        task_id="t1",
        tool_name="flaky",
        status="FAILED",
    )
    history.record_event(
        event_id="e3",
        plan_id="p_replan",
        event_type="AgentReplanRequested",
        replan_count=1,
        reason="Recoverable",
    )
    history.record_event(
        event_id="e4",
        plan_id="p_replan",
        event_type="AgentReplanned",
        replan_count=1,
        metadata={"new_tasks_count": 1},
    )
    history.record_event(
        event_id="e5",
        plan_id="p_replan",
        event_type="ToolExecuted",
        task_id="t2",
        tool_name="calc",
        status="SUCCESS",
    )
    history.record_event(
        event_id="e6", plan_id="p_replan", event_type="AgentPlanCompleted", status="SUCCESS"
    )

    tree = history.get_plan_execution_tree("p_replan")
    assert tree["status"] == "SUCCESS"
    assert "REPLAN #1" in tree["formatted_tree"]
    assert "Task t2 → SUCCESS (calc)" in tree["formatted_tree"]


def test_history_20_waiting_confirmation_execution_tree_reconstruction(
    tmp_db_path: str,
) -> None:
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    history = AgentExecutionHistoryStore(store=store)
    history.record_event(event_id="e1", plan_id="p_conf", event_type="AgentPlanCreated")
    history.record_event(
        event_id="e2",
        plan_id="p_conf",
        event_type="AgentPlanCompleted",
        status="WAITING_CONFIRMATION",
    )

    tree = history.get_plan_execution_tree("p_conf")
    assert tree["status"] == "WAITING_CONFIRMATION"


def test_history_21_cancelled_execution_tree_reconstruction(tmp_db_path: str) -> None:
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    history = AgentExecutionHistoryStore(store=store)
    history.record_event(event_id="e1", plan_id="p_cancel", event_type="AgentPlanCreated")
    history.record_event(
        event_id="e2",
        plan_id="p_cancel",
        event_type="AgentConfirmationDenied",
        task_id="t1",
        tool_name="danger",
    )
    history.record_event(
        event_id="e3", plan_id="p_cancel", event_type="AgentPlanCompleted", status="FAILED"
    )

    tree = history.get_plan_execution_tree("p_cancel")
    assert "CANCELLED/DENIED" in tree["formatted_tree"]


# -------------------------------------------------------------------
# SECURITY TESTS (22 - 24)
# -------------------------------------------------------------------


def test_security_22_secrets_are_not_persisted(tmp_db_path: str) -> None:
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    history = AgentExecutionHistoryStore(store=store)
    bus = EventBus()
    history.subscribe_to_bus(bus)

    # Publish security alert containing sensitive info
    bus.publish(
        AgentSecurityAlert(
            event_type="unauthorized_attempt",
            tool_name="dangerous",
            reason="Attempted authorization bypass",
            plan_id="p_sec",
        )
    )

    records = history.get_plan_history("p_sec")
    assert len(records) == 1
    # Check that raw password / token keys are not present in recorded metadata
    meta_keys = list(records[0]["metadata"].keys())
    assert "password" not in meta_keys
    assert "secret" not in meta_keys
    assert "api_key" not in meta_keys


def test_security_23_observability_components_do_not_execute_tools() -> None:
    is_fn = inspect.isfunction
    m_methods = [m[0] for m in inspect.getmembers(AgentMetricsCollector, predicate=is_fn)]
    h_methods = [m[0] for m in inspect.getmembers(AgentExecutionHistoryStore, predicate=is_fn)]

    assert "execute" not in m_methods
    assert "execute_tool" not in m_methods
    assert "execute" not in h_methods
    assert "execute_tool" not in h_methods


def test_security_24_no_eval_or_exec_in_stage5_modules() -> None:
    for cls in (AgentMetricsCollector, AgentExecutionHistoryStore):
        src = inspect.getsource(cls)
        assert "eval(" not in src
        assert "exec(" not in src
        assert "subprocess" not in src


# -------------------------------------------------------------------
# REGRESSION TEST (25)
# -------------------------------------------------------------------


def test_regression_25_end_to_end_agent_execution_with_observability(tmp_db_path: str) -> None:
    bus = EventBus()
    metrics = AgentMetricsCollector(event_bus=bus)
    store = SQLiteMemoryStore(db_path=tmp_db_path)
    history = AgentExecutionHistoryStore(store=store, event_bus=bus)

    registry = ToolRegistry()
    calc = DummyTool()
    registry.register(calc)

    llm = DummyLLM()
    planner = AgentPlanner(llm_provider=llm, registry=registry, event_bus=bus)
    plan = planner.create_plan("Calculate 1+1")

    executor = AgentExecutor(event_bus=bus, registry=registry)
    res = executor.execute_plan(plan)

    assert res.completed is True

    summary = metrics.get_summary()
    assert summary.plans_created == 1
    assert summary.plans_completed == 1
    assert summary.tasks_executed == 1
    assert summary.tasks_succeeded == 1

    tree = history.get_plan_execution_tree(plan.plan_id)
    assert tree["status"] == "SUCCESS"
    assert "Task" in tree["formatted_tree"]
