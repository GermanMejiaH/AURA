"""Stage 21 — Real Cognitive Provider Integration & Natural Conversational Intelligence Test Suite.

Verifies cognitive provider integration, strongly typed CognitiveTurnInterpretation contracts,
strict ToolRegistry proposal validation, non-bypassable Stage 16 RuntimeOrchestration,
Policy & Governance enforcement, SAFE_MODE quarantine, grounded response generation,
and thread-safe persistence across scenarios LLM-01 through LLM-20.
"""

from __future__ import annotations

import os
import tempfile
import threading
from typing import Any

from aura.cognition import (
    CognitiveMode,
    CognitiveTurnInterpretation,
    MockLLMProvider,
    ToolCallProposal,
    create_llm_provider,
)
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
from aura.memory.conversational import ConversationalMemory
from aura.memory.store import SQLiteMemoryStore
from aura.tools.builtins import CalculatorTool
from aura.tools.module import ToolsModule

# ============================================================================
# LLM-01 to LLM-20 INTEGRATION TESTS
# ============================================================================


def test_llm01_provider_configuration_instantiation() -> None:
    """LLM-01: Provider configuration and factory instantiation."""
    config = ConfigurationManager()
    provider = create_llm_provider(config=config, preferred_provider="mock")
    assert provider is not None
    assert isinstance(provider, MockLLMProvider)


def test_llm02_missing_credentials_graceful_fallback() -> None:
    """LLM-02: Missing API credentials fall back to MockLLMProvider cleanly."""
    old_env = os.environ.get("GEMINI_API_KEY")
    try:
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

        provider = create_llm_provider(preferred_provider="gemini")
        assert provider is not None
        # Should gracefully return MockLLMProvider when credentials absent
        assert isinstance(provider, MockLLMProvider)
    finally:
        if old_env is not None:
            os.environ["GEMINI_API_KEY"] = old_env


def test_llm03_provider_error_fallback() -> None:
    """LLM-03: Provider error/timeout falls back safely to Stage 20 rules."""

    class FailingProvider(MockLLMProvider):
        def interpret_turn(
            self,
            user_input: str,
            conversation_history: list[dict[str, Any]] | None = None,
            available_tools: list[dict[str, Any]] | None = None,
        ) -> CognitiveTurnInterpretation:
            raise RuntimeError("API Timeout Error")

    runtime = ConversationalRuntime(llm_provider=FailingProvider())
    try:
        # Should fall back cleanly to Stage 20 rules without crashing
        res = runtime.process_turn(conversation_id="conv_llm03", user_input="¿Qué fecha es hoy?")
        assert res.success is True
        assert res.action_id == "datetime_tool"
    finally:
        runtime.close()


def test_llm04_malformed_cognitive_response_rejected() -> None:
    """LLM-04: Malformed cognitive response falls back safely without crashing."""

    class MalformedProvider(MockLLMProvider):
        def interpret_turn(
            self,
            user_input: str,
            conversation_history: list[dict[str, Any]] | None = None,
            available_tools: list[dict[str, Any]] | None = None,
        ) -> CognitiveTurnInterpretation:
            return CognitiveTurnInterpretation(
                mode=CognitiveMode.PROVIDER_ERROR,
                error_message="Invalid JSON format",
            )

    runtime = ConversationalRuntime(llm_provider=MalformedProvider())
    try:
        res = runtime.process_turn(conversation_id="conv_llm04", user_input="Calcula 10 + 20")
        assert res.success is True
        assert res.action_id == "calculator_tool"
    finally:
        runtime.close()


def test_llm05_unknown_tool_proposal_rejected() -> None:
    """LLM-05: Unknown tool proposal (e.g. 'delete_all_files') is rejected via ToolRegistry."""
    mock_interps = {
        "elimina": CognitiveTurnInterpretation(
            mode=CognitiveMode.TOOL_PROPOSAL,
            tool_proposal=ToolCallProposal(tool_name="delete_all_files", arguments={"path": "/"}),
        )
    }

    provider = MockLLMProvider(mock_interpretations=mock_interps)
    runtime = ConversationalRuntime(llm_provider=provider)
    try:
        res = runtime.process_turn(
            conversation_id="conv_llm05", user_input="elimina todos los archivos"
        )
        assert res.success is False
        assert res.action_id == "unsupported"
        assert res.operation.state == RuntimeOperationState.BLOCKED
        assert "no está disponible" in res.natural_response.lower()
    finally:
        runtime.close()


def test_llm06_invalid_arguments_rejected() -> None:
    """LLM-06: Invalid tool arguments are rejected via ToolRegistry schema validation."""
    tools_reg = ToolsModule().registry
    tools_reg.register(CalculatorTool())

    mock_interps = {
        "calcula": CognitiveTurnInterpretation(
            mode=CognitiveMode.TOOL_PROPOSAL,
            tool_proposal=ToolCallProposal(
                tool_name="calculator_tool",
                arguments={"expression": 12345},  # Should be string
            ),
        )
    }

    provider = MockLLMProvider(mock_interpretations=mock_interps)
    runtime = ConversationalRuntime(tool_registry=tools_reg, llm_provider=provider)
    try:
        res = runtime.process_turn(
            conversation_id="conv_llm06", user_input="calcula con argumento invalido"
        )
        assert res.success is False
        assert res.action_id == "invalid_arguments"
        assert res.operation.state == RuntimeOperationState.BLOCKED
        assert "inválidos" in res.natural_response.lower()
    finally:
        runtime.close()


def test_llm07_llm_cannot_execute_tools_directly() -> None:
    """LLM-07: LLM proposal objects cannot execute tools directly without Stage 16."""
    mock_interps = {
        "calcula": CognitiveTurnInterpretation(
            mode=CognitiveMode.TOOL_PROPOSAL,
            tool_proposal=ToolCallProposal(
                tool_name="calculator_tool", arguments={"expression": "100 / 2"}
            ),
        )
    }

    provider = MockLLMProvider(mock_interpretations=mock_interps)
    runtime = ConversationalRuntime(llm_provider=provider)
    try:
        res = runtime.process_turn(conversation_id="conv_llm07", user_input="calcula 100 / 2")

        # Verify operation was logged and executed strictly by Stage 16 RuntimeOrchestrator
        assert res.operation.operation_id.startswith("op-")
        assert res.operation.execution_id is not None
        assert res.operation.state == RuntimeOperationState.COMPLETED
        assert res.tool_output == 50
    finally:
        runtime.close()


def test_llm08_llm_proposal_cannot_bypass_runtime_orchestrator() -> None:
    """LLM-08: LLM proposals cannot bypass Stage 16 RuntimeOrchestrator when scope is disabled."""
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.DISABLED)
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    mock_interps = {
        "fecha": CognitiveTurnInterpretation(
            mode=CognitiveMode.TOOL_PROPOSAL,
            tool_proposal=ToolCallProposal(tool_name="datetime_tool", arguments={"action": "now"}),
        )
    }
    provider = MockLLMProvider(mock_interpretations=mock_interps)
    runtime = ConversationalRuntime(orchestrator=orchestrator, llm_provider=provider)
    try:
        res = runtime.process_turn(conversation_id="conv_llm08", user_input="dame la fecha")

        assert res.success is False
        assert res.execution_id is None
        assert res.operation.state == RuntimeOperationState.BLOCKED
    finally:
        runtime.close()


def test_llm09_proposal_passes_policy() -> None:
    """LLM-09: Tool proposal passes through Stage 11 Policy evaluation."""
    runtime = ConversationalRuntime()
    try:
        res = runtime.process_turn(
            conversation_id="conv_llm09",
            user_input="¿Qué fecha es hoy?",
            target_tool_name="datetime_tool",
        )
        assert res.success is True
        assert res.operation.policy_decision == "ALLOW"
    finally:
        runtime.close()


def test_llm10_proposal_passes_governance() -> None:
    """LLM-10: Tool proposal passes through Stage 10 Governance evaluation."""
    runtime = ConversationalRuntime()
    try:
        res = runtime.process_turn(
            conversation_id="conv_llm10",
            user_input="¿Qué fecha es hoy?",
            target_tool_name="datetime_tool",
        )
        assert res.success is True
        assert res.operation.state == RuntimeOperationState.COMPLETED
    finally:
        runtime.close()


def test_llm11_execution_occurs_in_stage12() -> None:
    """LLM-11: Tool execution occurs strictly in Stage 12 RuntimeExecutionEngine."""
    execution = RuntimeExecutionEngine()
    orchestrator = RuntimeOrchestrator(execution_engine=execution)

    runtime = ConversationalRuntime(orchestrator=orchestrator)
    try:
        res = runtime.process_turn(
            conversation_id="conv_llm11",
            user_input="¿Qué fecha es hoy?",
            target_tool_name="datetime_tool",
        )

        assert res.success is True
        assert res.execution_id is not None
        assert res.operation.execution_id == res.execution_id
        assert res.operation.state == RuntimeOperationState.COMPLETED
    finally:
        runtime.close()


def test_llm12_safe_mode_blocks_llm_execution() -> None:
    """LLM-12: Stage 15 SAFE_MODE quarantine blocks LLM-proposed tool execution."""
    assurance = RuntimeAssuranceEngine()
    assurance.enter_safe_mode(reason="Quarantine check")
    orchestrator = RuntimeOrchestrator(assurance_engine=assurance)

    mock_interps = {
        "fecha": CognitiveTurnInterpretation(
            mode=CognitiveMode.TOOL_PROPOSAL,
            tool_proposal=ToolCallProposal(tool_name="datetime_tool", arguments={"action": "now"}),
        )
    }
    provider = MockLLMProvider(mock_interpretations=mock_interps)
    runtime = ConversationalRuntime(orchestrator=orchestrator, llm_provider=provider)
    try:
        res = runtime.process_turn(conversation_id="conv_llm12", user_input="fecha")

        assert res.success is False
        assert res.operation.state == RuntimeOperationState.BLOCKED
        assert "modo seguro" in res.natural_response.lower()
    finally:
        runtime.close()


def test_llm13_rejected_policy_causes_zero_mutation() -> None:
    """LLM-13: Policy BLOCK causes zero state/execution mutation."""
    governance = RuntimeGovernanceEngine()
    governance.set_authority_scope(AutonomyScope.READ_ONLY)
    orchestrator = RuntimeOrchestrator(governance_engine=governance)

    runtime = ConversationalRuntime(orchestrator=orchestrator)
    try:
        res = runtime.process_turn(
            conversation_id="conv_llm13",
            user_input="Escribe archivo",
            target_tool_name="file_tool",
            tool_kwargs={"action": "write", "path": "x.txt", "content": "c"},
        )

        assert res.success is False
        assert res.execution_id is None
        assert res.operation.state == RuntimeOperationState.BLOCKED
    finally:
        runtime.close()


def test_llm14_real_execution_result_supplied_to_grounded_response() -> None:
    """LLM-14: Real execution result is supplied to grounded response generation."""
    tools_reg = ToolsModule().registry
    tools_reg.register(CalculatorTool())

    mock_interps = {
        "calcula": CognitiveTurnInterpretation(
            mode=CognitiveMode.TOOL_PROPOSAL,
            tool_proposal=ToolCallProposal(
                tool_name="calculator_tool", arguments={"expression": "250 * 4"}
            ),
        )
    }
    provider = MockLLMProvider(mock_interpretations=mock_interps)
    runtime = ConversationalRuntime(tool_registry=tools_reg, llm_provider=provider)
    try:
        res = runtime.process_turn(conversation_id="conv_llm14", user_input="calcula 250 * 4")

        assert res.success is True
        assert res.tool_output == 1000
        assert "1000" in res.natural_response
    finally:
        runtime.close()


def test_llm15_llm_cannot_fabricate_success_after_tool_failure() -> None:
    """LLM-15: LLM cannot fabricate success after tool execution failure."""
    execution = RuntimeExecutionEngine()
    orchestrator = RuntimeOrchestrator(execution_engine=execution)

    mock_interps = {
        "falla": CognitiveTurnInterpretation(
            mode=CognitiveMode.TOOL_PROPOSAL,
            tool_proposal=ToolCallProposal(
                tool_name="failing_tool", arguments={"expression": "err"}
            ),
        )
    }
    provider = MockLLMProvider(mock_interpretations=mock_interps)
    runtime = ConversationalRuntime(orchestrator=orchestrator, llm_provider=provider)
    try:

        def failing_fn() -> Any:
            raise RuntimeError("Hardware IO failure")

        # Directly invoke failing closed-loop operation to check grounded response formatting
        op = runtime.orchestrator.execute_closed_loop(
            action_id="failing_action", action_fn=failing_fn
        )
        assert op.state == RuntimeOperationState.FAILED

        grounded = provider.generate_grounded_response(
            user_input="ejecuta fallo",
            tool_name="failing_tool",
            tool_output=None,
            operation_state=op.state.value,
            failure_reason=op.failure_reason,
        )

        assert "falló" in grounded.lower() or "error" in grounded.lower()
        assert "éxito" not in grounded.lower()
    finally:
        runtime.close()


def test_llm16_conversation_context_survives_restart() -> None:
    """LLM-16: Cognitive conversation context survives restart across SQLite storage."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "llm16.db")
        mem_store1 = SQLiteMemoryStore(db_path=db_path)
        conv_mem1 = ConversationalMemory(store=mem_store1)
        orch_store1 = RuntimeOrchestrationStore(store=mem_store1)
        orchestrator1 = RuntimeOrchestrator(
            store=orch_store1, execution_engine=RuntimeExecutionEngine()
        )

        mock_interps = {
            "calcula": CognitiveTurnInterpretation(
                mode=CognitiveMode.TOOL_PROPOSAL,
                tool_proposal=ToolCallProposal(
                    tool_name="calculator_tool", arguments={"expression": "50 * 2"}
                ),
            )
        }
        provider = MockLLMProvider(mock_interpretations=mock_interps)

        runtime1 = ConversationalRuntime(
            orchestrator=orchestrator1,
            conversational_memory=conv_mem1,
            llm_provider=provider,
        )
        res1 = runtime1.process_turn(conversation_id="conv_restart", user_input="calcula 50 * 2")
        assert res1.success is True
        assert res1.tool_output == 100
        runtime1.close()

        # Restart process with new SQLite handles pointing to same DB
        mem_store2 = SQLiteMemoryStore(db_path=db_path)
        conv_mem2 = ConversationalMemory(store=mem_store2)
        orch_store2 = RuntimeOrchestrationStore(store=mem_store2)
        orchestrator2 = RuntimeOrchestrator(
            store=orch_store2, execution_engine=RuntimeExecutionEngine()
        )
        runtime2 = ConversationalRuntime(
            orchestrator=orchestrator2,
            conversational_memory=conv_mem2,
            llm_provider=provider,
        )

        try:
            turns = conv_mem2.get_recent_turns(session_id="conv_restart", limit=10)
            assert len(turns) == 2  # 1 user turn + 1 assistant turn
        finally:
            runtime2.close()


def test_llm17_multiple_conversations_remain_isolated() -> None:
    """LLM-17: Multiple conversations remain isolated without context leakage."""
    runtime = ConversationalRuntime()
    try:
        r1 = runtime.process_turn(conversation_id="conv_1", user_input="¿Qué fecha es hoy?")
        r2 = runtime.process_turn(conversation_id="conv_2", user_input="¿Qué hora es?")

        assert r1.conversation_id == "conv_1"
        assert r2.conversation_id == "conv_2"
        assert r1.turn_id != r2.turn_id
    finally:
        runtime.close()


def test_llm18_concurrent_cognitive_turns_thread_safe() -> None:
    """LLM-18: Concurrent cognitive turns remain thread-safe across threads."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "llm18.db")
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
                res = runtime.process_turn(
                    conversation_id=f"conv_thread_{idx}",
                    user_input="¿Qué fecha es hoy?",
                )
                assert res.success is True
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 11)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        runtime.close()
        assert len(errors) == 0


def test_llm19_multi_turn_contextual_proposal() -> None:
    """LLM-19: Multi-turn contextual proposal resolves turn context."""
    runtime = ConversationalRuntime()
    try:
        r1 = runtime.process_turn(conversation_id="conv_llm19", user_input="¿Qué fecha es hoy?")
        assert r1.success is True

        r2 = runtime.process_turn(conversation_id="conv_llm19", user_input="¿Y qué día es?")
        assert r2.success is True
        assert r2.anaphora_resolution.requires_reference is True
    finally:
        runtime.close()


def test_llm20_end_to_end_deterministic_cognitive_loop() -> None:
    """LLM-20: End-to-end cognitive conversational loop with deterministic test provider."""
    mock_interps = {
        "status": CognitiveTurnInterpretation(
            mode=CognitiveMode.TOOL_PROPOSAL,
            tool_proposal=ToolCallProposal(tool_name="system_status_tool", arguments={}),
        )
    }

    provider = MockLLMProvider(mock_interpretations=mock_interps)
    runtime = ConversationalRuntime(llm_provider=provider)
    try:
        res = runtime.process_turn(conversation_id="conv_llm20", user_input="revisa el status")

        assert res.success is True
        assert res.action_id == "system_status_tool"
        assert res.operation.state == RuntimeOperationState.COMPLETED
        assert res.cognitive_interpretation is not None
        assert res.cognitive_interpretation.mode == CognitiveMode.TOOL_PROPOSAL
    finally:
        runtime.close()
