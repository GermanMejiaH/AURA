"""Stage 19 — Real Capability Vertical Slice & Product Gate Test Suite.

Verifies end-to-end user turn processing:
User Input -> IntentDetector -> GoalManager -> ToolRegistry -> Stage 16 -> Action Output
across 10 core scenarios (VS-01 to VS-10) using real components without artificial test mocks.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest

from aura.autonomy.module import AutonomyModule
from aura.cognition.scheduling import (
    AdaptationStatus,
    AssuranceStatus,
    AutonomyScope,
    RealCapabilityVerticalSlice,
    RuntimeAdaptivePolicyEngine,
    RuntimeAssuranceEngine,
    RuntimeExecutionEngine,
    RuntimeGovernanceEngine,
    RuntimeOperationState,
    RuntimeOrchestrationStore,
    RuntimeOrchestrator,
)
from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.events import EventBus
from aura.memory.store import SQLiteMemoryStore
from aura.tools.builtins import CalculatorTool
from aura.tools.module import ToolsModule

# ============================================================================
# VS-01 to VS-10 VERTICAL SLICE INTEGRATION TESTS
# ============================================================================


def test_vs01_happy_path_real_datetime_tool() -> None:
    """VS-01 Happy Path: Real user input -> Intent -> Goal -> DateTimeTool -> Closed Loop."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "vs01.db")
        config = ConfigurationManager()
        config.set("storage.sqlite_path", db_path)

        container = DependencyContainer()
        event_bus = EventBus()

        tools_mod = ToolsModule(config=config, container=container, event_bus=event_bus)
        tools_mod.initialize()

        autonomy_mod = AutonomyModule(config=config, container=container, event_bus=event_bus)
        autonomy_mod.initialize()
        autonomy_mod.start()

        runner = RealCapabilityVerticalSlice(
            orchestrator=autonomy_mod.orchestrator,
            tool_registry=tools_mod.registry,
            goal_manager=autonomy_mod.goals,
            event_bus=event_bus,
        )

        res = runner.process_turn(
            user_input="¿Qué fecha y hora es hoy?",
            target_tool_name="datetime_tool",
            tool_kwargs={"action": "now"},
        )

        assert res.success is True
        valid_intents = ("question", "information_request", "casual_conversation")
        assert res.intent.intent_type.value in valid_intents
        assert res.operation_id.startswith("op-")
        assert res.correlation_id.startswith("corr-")
        assert res.execution_id is not None
        assert res.outcome_id is not None
        assert res.operation.state == RuntimeOperationState.COMPLETED

        autonomy_mod.stop()
        autonomy_mod.shutdown()


def test_vs01b_happy_path_real_calculator_tool() -> None:
    """VS-01b Happy Path: Real math calculation turn using CalculatorTool."""
    tools_reg = ToolsModule().registry
    tools_reg.register(CalculatorTool())

    runner = RealCapabilityVerticalSlice(tool_registry=tools_reg)
    res = runner.process_turn(
        user_input="Calcula 25 * 4 + 10",
        target_tool_name="calculator_tool",
        tool_kwargs={"expression": "25 * 4 + 10"},
    )

    assert res.success is True
    assert res.operation.state == RuntimeOperationState.COMPLETED


def test_vs02_policy_blocked_operation() -> None:
    """VS-02: Operation blocked at Policy evaluation when scope or policy restricts it."""
    # Policy evaluation blocks unallowed operations
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.READ_ONLY)
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    runner = RealCapabilityVerticalSlice(orchestrator=orchestrator)
    res = runner.process_turn(
        user_input="Ejecuta accion bloqueada",
        target_tool_name="file_tool",
        tool_kwargs={"action": "write", "path": "test.txt", "content": "data"},
    )

    # Mutation blocked under READ_ONLY
    assert res.success is False
    assert res.operation.state == RuntimeOperationState.BLOCKED


def test_vs03_governance_blocked_operation() -> None:
    """VS-03: Governance DISABLED scope blocks action before execution."""
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.DISABLED)
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    runner = RealCapabilityVerticalSlice(orchestrator=orchestrator)
    res = runner.process_turn(
        user_input="Accion bloqueada por gobernanza",
        target_tool_name="datetime_tool",
    )

    assert res.success is False
    assert res.operation.state == RuntimeOperationState.BLOCKED
    assert res.execution_id is None


def test_vs04_execution_failure() -> None:
    """VS-04: Action failure during Stage 12 transitions operation state to FAILED."""
    execution = RuntimeExecutionEngine()
    orchestrator = RuntimeOrchestrator(execution_engine=execution)

    runner = RealCapabilityVerticalSlice(orchestrator=orchestrator)

    def failing_action() -> Any:
        raise RuntimeError("Simulated execution failure")

    res = runner.process_turn(
        user_input="Ejecuta accion fallida",
        action_fn=failing_action,
    )

    assert res.success is False
    assert res.operation.state == RuntimeOperationState.FAILED
    assert "Simulated execution failure" in str(res.error)


def test_vs05_assurance_safe_mode() -> None:
    """VS-05: Stage 15 SAFE_MODE quarantine blocks vertical slice operations."""
    assurance = RuntimeAssuranceEngine()
    assurance.enter_safe_mode(reason="Quarantine anomaly")
    orchestrator = RuntimeOrchestrator(assurance_engine=assurance)

    runner = RealCapabilityVerticalSlice(orchestrator=orchestrator)
    res = runner.process_turn(user_input="Turn en safe mode")

    assert res.success is False
    assert res.operation.state == RuntimeOperationState.BLOCKED
    assert res.operation.assurance_status == AssuranceStatus.SAFE_MODE.value


def test_vs06_correlation_id_propagation() -> None:
    """VS-06: Supplied correlation_id propagates across all closed-loop stages."""
    orchestrator = RuntimeOrchestrator()
    runner = RealCapabilityVerticalSlice(orchestrator=orchestrator)
    cid = "corr-stage19-vs06"

    res = runner.process_turn(
        user_input="Trazabilidad correlation id",
        correlation_id=cid,
    )

    assert res.correlation_id == cid
    assert res.operation.correlation_id == cid


def test_vs07_idempotency() -> None:
    """VS-07: Sequential executions with identical parameters create clean operation records."""
    orchestrator = RuntimeOrchestrator()
    runner = RealCapabilityVerticalSlice(orchestrator=orchestrator)

    res1 = runner.process_turn(user_input="Consulta idéntica 1")
    res2 = runner.process_turn(user_input="Consulta idéntica 2")

    assert res1.operation_id != res2.operation_id
    assert orchestrator.store.count_operations() == 2


def test_vs08_restart_recovery() -> None:
    """VS-08: Incomplete operation in SQLite database recovers as RECOVERY_REQUIRED."""
    mem_store = SQLiteMemoryStore(db_path=":memory:")
    store1 = RuntimeOrchestrationStore(store=mem_store)
    orchestrator1 = RuntimeOrchestrator(store=store1)

    op = orchestrator1.create_operation(action_id="act-vs08-crash")

    store2 = RuntimeOrchestrationStore(store=mem_store)
    orchestrator2 = RuntimeOrchestrator(store=store2)
    recovered = orchestrator2.recover_incomplete_operations()

    assert len(recovered) == 1
    assert recovered[0].operation_id == op.operation_id
    assert recovered[0].state == RuntimeOperationState.RECOVERY_REQUIRED


def test_vs09_hitl_adaptation_proposal() -> None:
    """VS-09: Adaptation proposals require explicit approval (APPROVED != APPLIED)."""
    adaptation = RuntimeAdaptivePolicyEngine()
    orchestrator = RuntimeOrchestrator(adaptation_engine=adaptation)
    runner = RealCapabilityVerticalSlice(orchestrator=orchestrator)

    res = runner.process_turn(user_input="Operacion con propuesta de adaptacion")
    assert res.adaptation_proposal_id is not None

    prop_id = res.adaptation_proposal_id
    # Unapproved apply fails
    with pytest.raises(PermissionError):
        adaptation.apply_adaptation(prop_id)

    # Approve
    approved = adaptation.approve_proposal(prop_id, operator_id="op-admin", reason="Approved")
    assert approved.status == AdaptationStatus.APPROVED
    assert approved.applied_at is None

    # Apply
    applied = adaptation.apply_adaptation(prop_id)
    assert applied.status == AdaptationStatus.APPLIED
    assert applied.applied_at is not None


def test_vs10_no_direct_execution_bypass() -> None:
    """VS-10: Turn cannot bypass Policy or Governance to invoke Execution directly."""
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.DISABLED)
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    runner = RealCapabilityVerticalSlice(orchestrator=orchestrator)
    res = runner.process_turn(user_input="Intento de bypass de gobernanza")

    # Bypassing governance is impossible; operation is blocked before execution
    assert res.success is False
    assert res.operation.state == RuntimeOperationState.BLOCKED
    assert res.execution_id is None
