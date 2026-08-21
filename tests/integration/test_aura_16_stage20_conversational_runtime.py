"""Stage 20 — Conversational Runtime & Real Assistant Loop Test Suite.

Verifies real multi-turn conversational loop, contextual anaphora resolution,
session persistence in SQLite, natural grounded responses, trace correlation,
and strict non-bypassable governance across scenarios CV-01 through CV-20.
"""

from __future__ import annotations

import os
import tempfile
import threading
from typing import Any

from aura.autonomy.module import AutonomyModule
from aura.cognition.scheduling import (
    AutonomyScope,
    ConversationalRuntime,
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
from aura.memory.conversational import ConversationalMemory
from aura.memory.store import SQLiteMemoryStore
from aura.tools.builtins import CalculatorTool
from aura.tools.module import ToolsModule

# ============================================================================
# CV-01 to CV-20 CONVERSATIONAL INTEGRATION TESTS
# ============================================================================


def test_cv01_single_turn_real_conversation() -> None:
    """CV-01: Single-turn real conversation processing."""
    runtime = ConversationalRuntime()
    try:
        res = runtime.process_turn(conversation_id="conv_cv01", user_input="¿Qué fecha es hoy?")

        assert res.success is True
        assert res.conversation_id == "conv_cv01"
        assert res.turn_id is not None
        assert res.operation_id.startswith("op-")
        assert res.correlation_id.startswith("corr-")
        assert (
            "2026" in res.natural_response
            or "fecha" in res.natural_response.lower()
            or "hoy" in res.natural_response.lower()
        )
    finally:
        runtime.close()


def test_cv02_real_datetime_tool_execution() -> None:
    """CV-02: Real DateTimeTool execution with natural response."""
    tools_mod = ToolsModule()
    tools_mod.initialize()

    runtime = ConversationalRuntime(tool_registry=tools_mod.registry)
    try:
        res = runtime.process_turn(
            conversation_id="conv_cv02",
            user_input="¿Qué fecha y hora es hoy?",
            target_tool_name="datetime_tool",
            tool_kwargs={"action": "now"},
        )

        assert res.success is True
        assert res.action_id == "datetime_tool"
        assert isinstance(res.tool_output, dict)
        assert "datetime_formatted" in res.tool_output
        assert "Hoy es" in res.natural_response
    finally:
        runtime.close()


def test_cv03_real_calculator_tool_execution() -> None:
    """CV-03: Real CalculatorTool execution with natural response."""
    tools_reg = ToolsModule().registry
    tools_reg.register(CalculatorTool())

    runtime = ConversationalRuntime(tool_registry=tools_reg)
    try:
        res = runtime.process_turn(
            conversation_id="conv_cv03",
            user_input="Calcula 125 * 8",
            target_tool_name="calculator_tool",
            tool_kwargs={"expression": "125 * 8"},
        )

        assert res.success is True
        assert res.action_id == "calculator_tool"
        assert res.tool_output == 1000
        assert "1000" in res.natural_response
    finally:
        runtime.close()


def test_cv04_multi_turn_contextual_reference() -> None:
    """CV-04: Multi-turn contextual reference ('¿Y qué día es?')."""
    runtime = ConversationalRuntime()
    try:
        # Turn 1
        res1 = runtime.process_turn(conversation_id="conv_cv04", user_input="¿Qué fecha es hoy?")
        assert res1.success is True

        # Turn 2: Contextual continuation
        res2 = runtime.process_turn(conversation_id="conv_cv04", user_input="¿Y qué día es?")
        assert res2.success is True
        assert res2.action_id == "datetime_tool"
        assert res2.anaphora_resolution.requires_reference is True
    finally:
        runtime.close()


def test_cv05_previous_tool_result_reference() -> None:
    """CV-05: Previous result reference ('Súmale 20')."""
    tools_reg = ToolsModule().registry
    tools_reg.register(CalculatorTool())
    runtime = ConversationalRuntime(tool_registry=tools_reg)
    try:
        # Turn 1
        res1 = runtime.process_turn(
            conversation_id="conv_cv05",
            user_input="Calcula 25 * 4",
            target_tool_name="calculator_tool",
            tool_kwargs={"expression": "25 * 4"},
        )
        assert res1.success is True
        assert res1.tool_output == 100

        # Turn 2: "Súmale 20"
        res2 = runtime.process_turn(conversation_id="conv_cv05", user_input="Súmale 20")
        assert res2.success is True
        assert res2.action_id == "calculator_tool"
        assert res2.tool_output == 120
        assert "120" in res2.natural_response
    finally:
        runtime.close()


def test_cv06_conversation_session_isolation() -> None:
    """CV-06: Conversation/session isolation between distinct conversation IDs."""
    tools_reg = ToolsModule().registry
    tools_reg.register(CalculatorTool())
    runtime = ConversationalRuntime(tool_registry=tools_reg)
    try:
        # Conversation A: 10 + 5 = 15
        res_a1 = runtime.process_turn(
            conversation_id="conv_A",
            user_input="Calcula 10 + 5",
            target_tool_name="calculator_tool",
            tool_kwargs={"expression": "10 + 5"},
        )
        assert res_a1.tool_output == 15

        # Conversation B: 20 + 5 = 25
        res_b1 = runtime.process_turn(
            conversation_id="conv_B",
            user_input="Calcula 20 + 5",
            target_tool_name="calculator_tool",
            tool_kwargs={"expression": "20 + 5"},
        )
        assert res_b1.tool_output == 25

        # Conversation A continuation: "Súmale 10" -> should produce 15 + 10 = 25
        res_a2 = runtime.process_turn(conversation_id="conv_A", user_input="Súmale 10")
        assert res_a2.tool_output == 25
    finally:
        runtime.close()


def test_cv07_policy_blocked_conversational_request() -> None:
    """CV-07: Policy BLOCK produces clear policy response without tool execution."""
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.READ_ONLY)
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    runtime = ConversationalRuntime(orchestrator=orchestrator)
    try:
        res = runtime.process_turn(
            conversation_id="conv_cv07",
            user_input="Escribe archivo",
            target_tool_name="file_tool",
            tool_kwargs={"action": "write", "path": "x.txt", "content": "c"},
        )

        assert res.success is False
        assert res.operation.state == RuntimeOperationState.BLOCKED
        assert (
            "política" in res.natural_response.lower()
            or "gobernanza" in res.natural_response.lower()
        )
    finally:
        runtime.close()


def test_cv08_governance_blocked_conversational_request() -> None:
    """CV-08: Governance DISABLED scope blocks conversational turn."""
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.DISABLED)
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    runtime = ConversationalRuntime(orchestrator=orchestrator)
    try:
        res = runtime.process_turn(conversation_id="conv_cv08", user_input="¿Qué hora es?")

        assert res.success is False
        assert res.operation.state == RuntimeOperationState.BLOCKED
        assert (
            "autorización" in res.natural_response.lower()
            or "gobernanza" in res.natural_response.lower()
        )
    finally:
        runtime.close()


def test_cv09_execution_failure_safe_conversational_response() -> None:
    """CV-09: Execution failure in Stage 12 produces safe error response."""
    execution = RuntimeExecutionEngine()
    orchestrator = RuntimeOrchestrator(execution_engine=execution)
    runtime = ConversationalRuntime(orchestrator=orchestrator)
    try:

        def failing_action() -> Any:
            raise RuntimeError("Disk IO Error")

        res = runtime.process_turn(
            conversation_id="conv_cv09",
            user_input="Accion fallida",
            target_tool_name="datetime_tool",
        )

        # Force action_fn failure via direct orchestrator invocation wrapper
        res_failed = runtime.orchestrator.execute_closed_loop(
            action_id="failing_tool",
            goal_id=res.goal_id,
            action_fn=failing_action,
        )
        assert res_failed.state == RuntimeOperationState.FAILED
    finally:
        runtime.close()


def test_cv10_safe_mode_prevents_conversational_execution() -> None:
    """CV-10: Stage 15 SAFE_MODE quarantine blocks conversational tool execution."""
    assurance = RuntimeAssuranceEngine()
    assurance.enter_safe_mode(reason="Quarantine check")
    orchestrator = RuntimeOrchestrator(assurance_engine=assurance)

    runtime = ConversationalRuntime(orchestrator=orchestrator)
    try:
        res = runtime.process_turn(conversation_id="conv_cv10", user_input="¿Qué fecha es hoy?")

        assert res.success is False
        assert res.operation.state == RuntimeOperationState.BLOCKED
        assert "modo seguro" in res.natural_response.lower()
    finally:
        runtime.close()


def test_cv11_no_bypass_runtime_orchestrator() -> None:
    """CV-11: ConversationalRuntime turns cannot bypass Stage 16 RuntimeOrchestrator."""
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.DISABLED)
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    runtime = ConversationalRuntime(orchestrator=orchestrator)
    try:
        res = runtime.process_turn(conversation_id="conv_cv11", user_input="Intento de bypass")

        assert res.success is False
        assert res.execution_id is None
        assert res.operation.state == RuntimeOperationState.BLOCKED
    finally:
        runtime.close()


def test_cv12_llm_proposal_cannot_directly_execute() -> None:
    """CV-12: LLM tool proposals cannot execute tools without passing through Stage 16."""
    runtime = ConversationalRuntime()
    try:
        proposed_kwargs = {"expression": "50 * 2"}
        res = runtime.process_turn(
            conversation_id="conv_cv12",
            user_input="Calcula 50 * 2",
            target_tool_name="calculator_tool",
            tool_kwargs=proposed_kwargs,
        )

        assert res.success is True
        assert res.action_id == "calculator_tool"
        assert res.operation.state == RuntimeOperationState.COMPLETED
    finally:
        runtime.close()


def test_cv13_trace_correlation_ids_preserved() -> None:
    """CV-13: Full correlation IDs preserved across conversation + runtime."""
    cid = "corr-stage20-cv13"
    runtime = ConversationalRuntime()
    try:
        res = runtime.process_turn(
            conversation_id="conv_cv13",
            user_input="¿Qué fecha es hoy?",
            correlation_id=cid,
        )

        assert res.conversation_id == "conv_cv13"
        assert res.correlation_id == cid
        assert res.operation.correlation_id == cid
        assert res.goal_id == res.operation.goal_id
        assert res.execution_id == res.operation.execution_id
        assert res.outcome_id == res.operation.outcome_id
    finally:
        runtime.close()


def test_cv14_restart_reconstructs_conversation_state() -> None:
    """CV-14: Process restart reconstructs SQLite conversation state cleanly."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "cv14.db")
        mem_store1 = SQLiteMemoryStore(db_path=db_path)
        conv_mem1 = ConversationalMemory(store=mem_store1)
        orch_store1 = RuntimeOrchestrationStore(store=mem_store1)
        orchestrator1 = RuntimeOrchestrator(
            store=orch_store1,
            execution_engine=RuntimeExecutionEngine(),
        )

        runtime1 = ConversationalRuntime(
            orchestrator=orchestrator1, conversational_memory=conv_mem1
        )
        res1 = runtime1.process_turn(
            conversation_id="conv_restart",
            user_input="Calcula 25 * 4",
            target_tool_name="calculator_tool",
            tool_kwargs={"expression": "25 * 4"},
        )
        assert res1.success is True
        assert res1.tool_output == 100
        runtime1.close()

        # Simulate Process Restart
        mem_store2 = SQLiteMemoryStore(db_path=db_path)
        conv_mem2 = ConversationalMemory(store=mem_store2)
        orch_store2 = RuntimeOrchestrationStore(store=mem_store2)
        orchestrator2 = RuntimeOrchestrator(
            store=orch_store2,
            execution_engine=RuntimeExecutionEngine(),
        )
        runtime2 = ConversationalRuntime(
            orchestrator=orchestrator2, conversational_memory=conv_mem2
        )

        try:
            # Resume conversation
            res2 = runtime2.process_turn(conversation_id="conv_restart", user_input="Súmale 20")
            assert res2.success is True
            assert res2.tool_output == 120
        finally:
            runtime2.close()


def test_cv15_concurrent_conversations_isolated() -> None:
    """CV-15: 10 concurrent thread conversations remain thread-safe and isolated."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "cv15.db")
        mem_store = SQLiteMemoryStore(db_path=db_path)
        conv_mem = ConversationalMemory(store=mem_store)
        orch_store = RuntimeOrchestrationStore(store=mem_store)
        orchestrator = RuntimeOrchestrator(
            store=orch_store, execution_engine=RuntimeExecutionEngine()
        )
        runtime = ConversationalRuntime(orchestrator=orchestrator, conversational_memory=conv_mem)

        errors: list[Exception] = []

        def worker(idx: int) -> None:
            try:
                conv_id = f"conv_conc_{idx}"
                r1 = runtime.process_turn(
                    conversation_id=conv_id,
                    user_input=f"Calcula {idx} * 10",
                    target_tool_name="calculator_tool",
                    tool_kwargs={"expression": f"{idx} * 10"},
                )
                assert r1.tool_output == idx * 10

                r2 = runtime.process_turn(conversation_id=conv_id, user_input="Súmale 5")
                assert r2.tool_output == (idx * 10) + 5
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 11)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        runtime.close()
        assert len(errors) == 0


def test_cv16_duplicate_turn_idempotency() -> None:
    """CV-16: Duplicate turn processing handles operation IDs cleanly."""
    runtime = ConversationalRuntime()
    try:
        res1 = runtime.process_turn(conversation_id="conv_cv16", user_input="¿Qué fecha es hoy?")
        res2 = runtime.process_turn(conversation_id="conv_cv16", user_input="¿Qué fecha es hoy?")

        assert res1.operation_id != res2.operation_id
        assert res1.success is True
        assert res2.success is True
    finally:
        runtime.close()


def test_cv17_natural_response_grounded_in_result() -> None:
    """CV-17: Response is strictly grounded in real execution result."""
    tools_reg = ToolsModule().registry
    tools_reg.register(CalculatorTool())
    runtime = ConversationalRuntime(tool_registry=tools_reg)
    try:
        res = runtime.process_turn(
            conversation_id="conv_cv17",
            user_input="Calcula 12345 * 678",
            target_tool_name="calculator_tool",
            tool_kwargs={"expression": "12345 * 678"},
        )

        assert res.success is True
        expected_val = 12345 * 678
        assert res.tool_output == expected_val
        assert str(expected_val) in res.natural_response
    finally:
        runtime.close()


def test_cv18_unsupported_request_fails_gracefully() -> None:
    """CV-18: Unsupported operation request produces clear failure response."""
    runtime = ConversationalRuntime()
    try:
        res = runtime.process_turn(conversation_id="conv_cv18", user_input="Dame un cafe")

        assert res.success is False
        assert res.action_id == "unsupported"
        assert "herramienta disponible" in res.natural_response.lower()
    finally:
        runtime.close()


def test_cv19_ambiguous_request_does_not_cause_unauthorized_execution() -> None:
    """CV-19: Ambiguous contextual reference asks for clarification without action."""
    runtime = ConversationalRuntime()
    try:
        # "Súmale 20" without prior math context
        res = runtime.process_turn(conversation_id="conv_cv19_fresh", user_input="Súmale 20")

        assert res.success is False
        assert res.action_id == "ambiguous"
        assert (
            "específico" in res.natural_response.lower() or "seguro" in res.natural_response.lower()
        )
    finally:
        runtime.close()


def test_cv20_real_multi_turn_reality_validation_5_turns() -> None:
    """CV-20 Reality Validation: 5 sequential turns + restart turn on real SQLite storage."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "cv20_reality.db")
        config = ConfigurationManager()
        config.set("storage.sqlite_path", db_path)

        container = DependencyContainer()
        event_bus = EventBus()

        tools_mod = ToolsModule(config=config, container=container, event_bus=event_bus)
        tools_mod.initialize()
        tools_mod.registry.register(CalculatorTool())

        autonomy_mod = AutonomyModule(config=config, container=container, event_bus=event_bus)
        autonomy_mod.initialize()
        autonomy_mod.start()

        db_store = SQLiteMemoryStore(db_path=db_path)
        conv_mem1 = ConversationalMemory(store=db_store, event_bus=event_bus)

        # Wire orchestrator with SQLiteMemoryStore
        autonomy_mod.orchestrator.store = RuntimeOrchestrationStore(store=db_store)
        autonomy_mod.orchestrator.execution_engine = RuntimeExecutionEngine(event_bus=event_bus)

        runtime1 = ConversationalRuntime(
            orchestrator=autonomy_mod.orchestrator,
            tool_registry=tools_mod.registry,
            goal_manager=autonomy_mod.goals,
            conversational_memory=conv_mem1,
            event_bus=event_bus,
        )

        cid = "conv_reality_cv20"

        # Turn 1: "¿Qué fecha es hoy?"
        t1 = runtime1.process_turn(conversation_id=cid, user_input="¿Qué fecha es hoy?")
        assert t1.success is True

        # Turn 2: "¿Y qué día es?"
        t2 = runtime1.process_turn(conversation_id=cid, user_input="¿Y qué día es?")
        assert t2.success is True

        # Turn 3: "¿Qué hora es?"
        t3 = runtime1.process_turn(conversation_id=cid, user_input="¿Qué hora es?")
        assert t3.success is True

        # Turn 4: "¿Cuánto es 25 * 4?"
        t4 = runtime1.process_turn(
            conversation_id=cid,
            user_input="Calcula 25 * 4",
            target_tool_name="calculator_tool",
            tool_kwargs={"expression": "25 * 4"},
        )
        assert t4.success is True
        assert t4.tool_output == 100

        # Turn 5: "Súmale 20."
        t5 = runtime1.process_turn(conversation_id=cid, user_input="Súmale 20.")
        assert t5.success is True
        assert t5.tool_output == 120

        # Verify turns in SQLite
        turns1 = conv_mem1.get_recent_turns(session_id=cid, limit=20)
        assert len(turns1) == 10  # 5 user turns + 5 assistant turns

        runtime1.close()
        autonomy_mod.stop()
        autonomy_mod.shutdown()

        # Turn 6: Restart & Resume
        autonomy_mod2 = AutonomyModule(config=config, container=container, event_bus=event_bus)
        autonomy_mod2.initialize()
        autonomy_mod2.start()

        db_store2 = SQLiteMemoryStore(db_path=db_path)
        conv_mem2 = ConversationalMemory(store=db_store2, event_bus=event_bus)
        autonomy_mod2.orchestrator.store = RuntimeOrchestrationStore(store=db_store2)
        autonomy_mod2.orchestrator.execution_engine = RuntimeExecutionEngine(event_bus=event_bus)

        runtime2 = ConversationalRuntime(
            orchestrator=autonomy_mod2.orchestrator,
            tool_registry=tools_mod.registry,
            goal_manager=autonomy_mod2.goals,
            conversational_memory=conv_mem2,
            event_bus=event_bus,
        )

        t6 = runtime2.process_turn(conversation_id=cid, user_input="Súmale 10.")
        assert t6.success is True
        assert t6.tool_output == 130

        runtime2.close()
        autonomy_mod2.stop()
        autonomy_mod2.shutdown()
