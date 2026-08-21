"""Stage 21 — Conversational Runtime & Real Cognitive Provider Loop.

Provides a multi-turn, context-aware, persistent conversational loop linking:
User Turn -> ConversationalMemory -> AnaphoraResolver -> IntentDetector
          -> LLM Provider -> Tool Proposal Validation -> Stage 16 RuntimeOrchestrator
          -> Policy -> Governance -> Execution -> Experience -> Adaptation -> Assurance
          -> LLM Grounded Response
while preserving Stage 10-20 contracts & ensuring zero executive authority for LLM.
"""

from __future__ import annotations

import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aura.cognition.cognitive_contract import (
    CognitiveMode,
    CognitiveTurnInterpretation,
)
from aura.cognition.conversation_context import AnaphoraResolution, AnaphoraResolver
from aura.cognition.goals import GoalManager, PersistentGoal
from aura.cognition.intent import Intent, IntentDetector
from aura.cognition.proactive import (
    ActionProposal,
    ProactiveNotification,
    ProactiveTask,
    ProactiveTaskEvaluator,
    ProactiveTaskStatus,
    ProactiveTaskStore,
    TriggerDefinition,
    TriggerType,
)
from aura.cognition.provider import LLMProvider, MockLLMProvider
from aura.cognition.session import SessionContext, SessionManager
from aura.events import EventBus
from aura.logging import get_logger
from aura.memory.conversational import ConversationalMemory, ConversationTurn
from aura.tools.base import ToolResult
from aura.tools.module import ToolsModule
from aura.tools.registry import ToolRegistry

from .assurance import AssuranceStatus
from .execution import RuntimeExecutionEngine
from .orchestration import RuntimeOperation, RuntimeOperationState, RuntimeOrchestrator

logger = get_logger("ConversationalRuntime")


@dataclass(frozen=True)
class ConversationalTurnResult:
    """Immutable result emitted by ConversationalRuntime processing turn."""

    conversation_id: str
    turn_id: str
    user_input: str
    intent: Intent
    anaphora_resolution: AnaphoraResolution
    goal_id: str
    action_id: str
    operation_id: str
    correlation_id: str
    execution_id: str | None
    outcome_id: str | None
    adaptation_proposal_id: str | None
    tool_output: Any
    natural_response: str
    success: bool
    error: str | None
    operation: RuntimeOperation
    cognitive_interpretation: CognitiveTurnInterpretation | None = None


class ConversationalRuntime:
    """Thread-safe multi-turn conversational runtime adapter delegating execution to Stage 16."""

    def __init__(
        self,
        orchestrator: RuntimeOrchestrator | None = None,
        tool_registry: ToolRegistry | None = None,
        goal_manager: GoalManager | None = None,
        conversational_memory: ConversationalMemory | None = None,
        session_manager: SessionManager | None = None,
        llm_provider: LLMProvider | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.orchestrator = orchestrator or RuntimeOrchestrator(
            execution_engine=RuntimeExecutionEngine(event_bus=event_bus),
            event_bus=event_bus,
        )

        if tool_registry is not None:
            self.tool_registry = tool_registry
        else:
            tools_mod = ToolsModule(event_bus=event_bus)
            tools_mod.initialize()
            self.tool_registry = tools_mod.registry

        self.goal_manager = goal_manager or GoalManager(event_bus=event_bus)
        self.conversational_memory = conversational_memory or ConversationalMemory(
            event_bus=event_bus
        )
        self.session_manager = session_manager or SessionManager(event_bus=event_bus)

        if llm_provider is not None:
            self.llm_provider = llm_provider
        else:
            self.llm_provider = MockLLMProvider()

        # Proactive task persistence & evaluation engine
        if (
            self.conversational_memory
            and hasattr(self.conversational_memory, "store")
            and hasattr(self.conversational_memory.store, "store")
        ):
            shared_store = self.conversational_memory.store.store
        else:
            shared_store = None

        self.proactive_store = ProactiveTaskStore(store=shared_store)
        self.proactive_evaluator = ProactiveTaskEvaluator(
            orchestrator=self.orchestrator,
            tool_registry=self.tool_registry,
            store=self.proactive_store,
            event_bus=self.event_bus,
        )

        self._lock = threading.RLock()

    def create_proactive_task(
        self,
        conversation_id: str,
        trigger_type: TriggerType,
        trigger_definition: TriggerDefinition,
        action_proposal: ActionProposal,
        max_executions: int = 1,
        creation_turn_id: str = "turn_0",
        metadata: dict[str, Any] | None = None,
    ) -> ProactiveTask:
        """Creates and persists a new proactive task in SQLite."""
        task = ProactiveTask(
            conversation_id=conversation_id,
            creation_turn_id=creation_turn_id,
            trigger_type=trigger_type,
            trigger_definition=trigger_definition,
            action_proposal=action_proposal,
            status=ProactiveTaskStatus.PENDING,
            max_executions=max_executions,
            metadata=metadata or {},
        )
        self.proactive_store.save_task(task)
        return task

    def evaluate_proactive_tasks(self, **kwargs: Any) -> list[ProactiveNotification]:
        """Evaluates active proactive tasks and dispatches proposals strictly via Stage 16."""
        return self.proactive_evaluator.evaluate_active_tasks(**kwargs)

    def list_proactive_tasks(
        self,
        conversation_id: str | None = None,
        status: ProactiveTaskStatus | str | None = None,
    ) -> list[ProactiveTask]:
        """Lists proactive tasks filtered by conversation or status."""
        return self.proactive_store.list_tasks(conversation_id=conversation_id, status=status)

    def cancel_proactive_task(self, task_id: str, reason: str = "Manual user cancellation") -> bool:
        """Cancels a pending or active proactive task."""
        return self.proactive_store.cancel_task(task_id=task_id, reason=reason)

    def cancel_all_proactive_tasks(
        self, conversation_id: str, reason: str = "Batch user cancellation"
    ) -> int:
        """Cancels all pending/active proactive tasks for a conversation."""
        return self.proactive_store.cancel_all_tasks(conversation_id=conversation_id, reason=reason)

    def get_proactive_notifications(
        self, conversation_id: str | None = None, undelivered_only: bool = False
    ) -> list[ProactiveNotification]:
        """Retrieves grounded proactive result notifications."""
        return self.proactive_store.list_notifications(
            conversation_id=conversation_id, undelivered_only=undelivered_only
        )

    def close(self) -> None:
        """Flushes and closes underlying SQLite connection stores cleanly."""
        with self._lock:
            if self.conversational_memory and self.conversational_memory.store:
                self.conversational_memory.store.close()
            if (
                self.orchestrator
                and hasattr(self.orchestrator, "store")
                and hasattr(self.orchestrator.store, "store")
            ):
                self.orchestrator.store.store.close()

    def process_turn(
        self,
        conversation_id: str,
        user_input: str,
        correlation_id: str | None = None,
        target_tool_name: str | None = None,
        tool_kwargs: dict[str, Any] | None = None,
    ) -> ConversationalTurnResult:
        """Processes a multi-turn user conversation input through Stage 16 pipeline."""
        with self._lock:
            # 1. Session Setup & Persistence Check
            if not self.conversational_memory.session_exists(conversation_id):
                self.conversational_memory.create_session(
                    session_id=conversation_id, title=f"Session {conversation_id[:8]}"
                )

            # Record turn count in RAM session manager
            self.session_manager.record_turn()
            session_ctx: SessionContext = self.session_manager.get_context()

            # 2. Retrieve Conversation History for Anaphora & Context Resolution
            recent_turns: list[ConversationTurn] = self.conversational_memory.get_recent_turns(
                session_id=conversation_id, limit=20
            )

            recent_entities: list[str] = []
            last_tool_output: Any = None
            last_action_id: str | None = None
            history_formatted: list[dict[str, Any]] = []

            for turn in reversed(recent_turns):
                history_formatted.append({"role": turn.role, "content": turn.content})
                if turn.role == "assistant" and turn.metadata:
                    if "tool_output" in turn.metadata and last_tool_output is None:
                        last_tool_output = turn.metadata["tool_output"]
                    if "action_id" in turn.metadata and last_action_id is None:
                        last_action_id = str(turn.metadata["action_id"])
                if turn.role == "user" and turn.metadata and "resolved_entity" in turn.metadata:
                    recent_entities.append(str(turn.metadata["resolved_entity"]))

            # 3. Anaphora & Contextual Reference Resolution
            anaphora_res = AnaphoraResolver.analyze(
                user_input=user_input,
                recent_entities=recent_entities,
                active_topic=session_ctx.current_topic,
                active_entity=session_ctx.active_entity,
            )

            # 4. Intent Detection
            intent = IntentDetector.detect(user_input)
            self.session_manager.update_intent(intent)

            # 5. Cognitive Interpretation via LLM Provider or Stage 20 Heuristic Fallback
            cognitive_interp: CognitiveTurnInterpretation | None = None
            resolved_tool_name: str = "none"
            resolved_kwargs: dict[str, Any] = {}
            resolved_entity: str | None = None
            direct_response_text: str | None = None

            now_iso = (
                self.orchestrator.clock.now_iso() if hasattr(self.orchestrator, "clock") else ""
            )
            op_id = f"op-{uuid.uuid4().hex[:8]}"
            cid = correlation_id or f"corr-{uuid.uuid4().hex[:8]}"

            use_cognitive_provider = False
            if self.llm_provider:
                if isinstance(self.llm_provider, MockLLMProvider):
                    if self.llm_provider.mock_interpretations:
                        use_cognitive_provider = True
                else:
                    use_cognitive_provider = True

            # Check explicit parameter overrides first
            if target_tool_name:
                resolved_tool_name = target_tool_name
                resolved_kwargs = tool_kwargs or {}
            elif use_cognitive_provider:
                # Retrieve available tool schemas for LLM cognitive proposal
                available_tools_schema = [
                    {
                        "name": meta.name,
                        "description": meta.description,
                        "parameters_schema": meta.parameters_schema,
                    }
                    for meta in self.tool_registry.list_metadata()
                ]

                try:
                    cognitive_interp = self.llm_provider.interpret_turn(
                        user_input=user_input,
                        conversation_history=history_formatted,
                        available_tools=available_tools_schema,
                    )
                except Exception as exc:
                    logger.warning(f"Cognitive provider interpret_turn failed: {exc}")
                    cognitive_interp = CognitiveTurnInterpretation(
                        mode=CognitiveMode.PROVIDER_ERROR,
                        error_message=str(exc),
                    )

                if cognitive_interp and cognitive_interp.mode == CognitiveMode.TOOL_PROPOSAL:
                    if cognitive_interp.tool_proposal:
                        prop_name = cognitive_interp.tool_proposal.tool_name.strip().lower()
                        prop_args = cognitive_interp.tool_proposal.arguments or {}

                        # PHASE 5 TOOL PROPOSAL VALIDATION
                        tool_obj = self.tool_registry.get(prop_name)
                        if tool_obj is None:
                            resolved_tool_name = "unsupported"
                            direct_response_text = (
                                f"La herramienta '{prop_name}' propuesta no está disponible en"
                                " ToolRegistry."
                            )
                        else:
                            valid, val_err = self.tool_registry.validate_parameters(
                                prop_name, **prop_args
                            )
                            if not valid:
                                resolved_tool_name = "invalid_arguments"
                                direct_response_text = (
                                    f"Los argumentos para la herramienta '{prop_name}' son"
                                    f" inválidos: {val_err}."
                                )
                            else:
                                resolved_tool_name = prop_name
                                resolved_kwargs = prop_args
                elif (
                    cognitive_interp
                    and cognitive_interp.mode == CognitiveMode.CLARIFICATION_REQUIRED
                ):
                    resolved_tool_name = "clarification"
                    direct_response_text = (
                        cognitive_interp.direct_response or "Por favor proporciona más información."
                    )
                elif cognitive_interp and cognitive_interp.mode == CognitiveMode.UNSUPPORTED:
                    resolved_tool_name = "unsupported"
                    direct_response_text = (
                        cognitive_interp.direct_response
                        or "No tengo una herramienta disponible para realizar esa operación."
                    )
                elif cognitive_interp and cognitive_interp.mode == CognitiveMode.DIRECT_RESPONSE:
                    resolved_tool_name = "direct_response"
                    direct_response_text = (
                        cognitive_interp.direct_response or f"Entendido: {user_input}"
                    )

            # Stage 20 heuristic fallback if tool unassigned or provider in mock/fallback
            if resolved_tool_name in ("none", ""):
                r_name, r_kwargs, r_ent = self._resolve_tool_proposal(
                    user_input=user_input,
                    intent=intent,
                    anaphora_res=anaphora_res,
                    last_tool_output=last_tool_output,
                    last_action_id=last_action_id,
                    target_tool_name=target_tool_name,
                    tool_kwargs=tool_kwargs,
                )
                resolved_tool_name = r_name
                resolved_kwargs = r_kwargs
                resolved_entity = r_ent

            # 6. Check for Unsupported, Ambiguous, Invalid, or Direct Responses BEFORE execution
            if resolved_tool_name in (
                "unsupported",
                "ambiguous",
                "invalid_arguments",
                "clarification",
                "direct_response",
            ):
                goal = self.goal_manager.create_goal(
                    description=f"Conversational turn: {user_input[:50]}"
                )
                natural_resp = direct_response_text or (
                    "No tengo una herramienta disponible para realizar esa operación todavía."
                    if resolved_tool_name == "unsupported"
                    else "No estoy seguro de qué resultado quieres modificar. ¿Podrías ser más"
                    " específico?"
                )

                user_turn = self.conversational_memory.add_turn(
                    session_id=conversation_id,
                    role="user",
                    content=user_input,
                    intent_type=intent.intent_type.value,
                )
                self.conversational_memory.add_turn(
                    session_id=conversation_id,
                    role="assistant",
                    content=natural_resp,
                    intent_type="response",
                )
                empty_op = RuntimeOperation(
                    operation_id=op_id,
                    correlation_id=cid,
                    goal_id=goal.goal_id,
                    action_id=resolved_tool_name,
                    created_at=now_iso,
                    state=RuntimeOperationState.COMPLETED
                    if resolved_tool_name == "direct_response"
                    else RuntimeOperationState.BLOCKED,
                    failure_reason=None
                    if resolved_tool_name == "direct_response"
                    else natural_resp,
                )
                return ConversationalTurnResult(
                    conversation_id=conversation_id,
                    turn_id=user_turn.turn_id,
                    user_input=user_input,
                    intent=intent,
                    anaphora_resolution=anaphora_res,
                    goal_id=goal.goal_id,
                    action_id=resolved_tool_name,
                    operation_id=empty_op.operation_id,
                    correlation_id=empty_op.correlation_id,
                    execution_id=None,
                    outcome_id=None,
                    adaptation_proposal_id=None,
                    tool_output=None,
                    natural_response=natural_resp,
                    success=resolved_tool_name == "direct_response",
                    error=None if resolved_tool_name == "direct_response" else natural_resp,
                    operation=empty_op,
                    cognitive_interpretation=cognitive_interp,
                )

            # 7. Create Goal & Unique Action Proposal for Orchestrator Execution
            goal_desc = f"Conversational turn: {user_input[:50]}"
            persistent_goal: PersistentGoal = self.goal_manager.create_goal(description=goal_desc)
            goal_id = persistent_goal.goal_id

            # Pass unique action_id to orchestrator so idempotency key is unique per turn
            action_id_unique = f"{resolved_tool_name}_{uuid.uuid4().hex[:6]}"

            tool = self.tool_registry.get(resolved_tool_name)
            output_container: dict[str, Any] = {}

            if tool is not None:

                def _real_action() -> Any:
                    tool_res: ToolResult = tool.execute(**resolved_kwargs)
                    if not tool_res.success:
                        raise RuntimeError(
                            tool_res.error or f"Tool '{resolved_tool_name}' execution failed"
                        )
                    output_container["result"] = tool_res.output
                    return tool_res.output

                action_fn: Callable[[], Any] = _real_action
            else:

                def _default_action() -> Any:
                    res = f"Executed default turn for '{resolved_tool_name}'"
                    output_container["result"] = res
                    return res

                action_fn = _default_action

            # 8. Dispatch Closed-Loop Execution through Stage 16 RuntimeOrchestrator
            operation = self.orchestrator.execute_closed_loop(
                action_id=action_id_unique,
                goal_id=goal_id,
                correlation_id=correlation_id,
                action_fn=action_fn,
                metadata={
                    "conversation_id": conversation_id,
                    "user_input": user_input,
                    "intent_type": intent.intent_type.value,
                    "tool_name": resolved_tool_name,
                    "tool_kwargs": resolved_kwargs,
                },
            )

            success = operation.state == RuntimeOperationState.COMPLETED
            err_msg = operation.failure_reason if not success else None

            # Retrieve raw tool output from execution container
            raw_tool_output: Any = output_container.get("result") if success else None

            # 9. Natural Grounded Response Generation
            if use_cognitive_provider and self.llm_provider:
                try:
                    natural_response = self.llm_provider.generate_grounded_response(
                        user_input=user_input,
                        tool_name=resolved_tool_name,
                        tool_output=raw_tool_output,
                        operation_state=operation.state.value,
                        failure_reason=operation.failure_reason,
                    )
                except Exception as exc:
                    logger.warning(f"Grounded response generation failed: {exc}")
                    natural_response = self._generate_natural_response(
                        operation=operation,
                        tool_name=resolved_tool_name,
                        tool_output=raw_tool_output,
                        user_input=user_input,
                    )
            else:
                natural_response = self._generate_natural_response(
                    operation=operation,
                    tool_name=resolved_tool_name,
                    tool_output=raw_tool_output,
                    user_input=user_input,
                )

            # 10. Persist Conversation Turns in SQLite
            user_turn = self.conversational_memory.add_turn(
                session_id=conversation_id,
                role="user",
                content=user_input,
                intent_type=intent.intent_type.value,
                metadata={"resolved_entity": resolved_entity} if resolved_entity else {},
            )

            assistant_metadata = {
                "operation_id": operation.operation_id,
                "correlation_id": operation.correlation_id,
                "goal_id": operation.goal_id,
                "action_id": resolved_tool_name,
                "execution_id": operation.execution_id,
                "outcome_id": operation.outcome_id,
                "adaptation_proposal_id": operation.adaptation_proposal_id,
                "tool_output": raw_tool_output,
                "success": success,
            }

            self.conversational_memory.add_turn(
                session_id=conversation_id,
                role="assistant",
                content=natural_response,
                intent_type="response",
                metadata=assistant_metadata,
            )

            # Update RAM session context active entity if resolved
            if resolved_entity:
                self.session_manager.set_task(task=resolved_tool_name, detail=str(resolved_entity))

            return ConversationalTurnResult(
                conversation_id=conversation_id,
                turn_id=user_turn.turn_id,
                user_input=user_input,
                intent=intent,
                anaphora_resolution=anaphora_res,
                goal_id=goal_id,
                action_id=resolved_tool_name,
                operation_id=operation.operation_id,
                correlation_id=operation.correlation_id,
                execution_id=operation.execution_id,
                outcome_id=operation.outcome_id,
                adaptation_proposal_id=operation.adaptation_proposal_id,
                tool_output=raw_tool_output,
                natural_response=natural_response,
                success=success,
                error=err_msg,
                operation=operation,
                cognitive_interpretation=cognitive_interp,
            )

    def _resolve_tool_proposal(
        self,
        user_input: str,
        intent: Intent,
        anaphora_res: AnaphoraResolution,
        last_tool_output: Any,
        last_action_id: str | None,
        target_tool_name: str | None,
        tool_kwargs: dict[str, Any] | None,
    ) -> tuple[str, dict[str, Any], str | None]:
        """Formulates tool proposal & parameter kwargs from input and context."""
        if target_tool_name:
            return target_tool_name, tool_kwargs or {}, None

        text_clean = user_input.strip().lower()

        # Check explicit unsupported operations like "dame un cafe" or "vuela a la luna"
        if re.search(
            r"\b(?:caf[eé]|vuela|viaja|teletransporta|compra|paga)\b",
            text_clean,
            re.IGNORECASE,
        ):
            return "unsupported", {}, None

        # Math Continuation detection ("Súmale 20", "Calcula 25 * 4", "Súmale 10")
        sum_match = re.search(
            r"\b(?:s[uú]male|agrega|adiciona|\+)\s+(\d+(?:\.\d+)?)\b",
            text_clean,
            re.IGNORECASE,
        )
        if sum_match:
            added_val = sum_match.group(1)
            if last_tool_output is not None and (
                isinstance(last_tool_output, (int, float))
                or str(last_tool_output).replace(".", "", 1).isnumeric()
            ):
                expr = f"{last_tool_output} + {added_val}"
                return "calculator_tool", {"expression": expr}, str(added_val)
            else:
                return "ambiguous", {}, None

        mult_match = re.search(
            r"\b(?:multiplica(?:lo)?\s+por|\*)\s+(\d+(?:\.\d+)?)\b",
            text_clean,
            re.IGNORECASE,
        )
        if mult_match:
            mult_val = mult_match.group(1)
            if last_tool_output is not None and (
                isinstance(last_tool_output, (int, float))
                or str(last_tool_output).replace(".", "", 1).isnumeric()
            ):
                expr = f"{last_tool_output} * {mult_val}"
                return "calculator_tool", {"expression": expr}, str(mult_val)
            else:
                return "ambiguous", {}, None

        # Direct math expression: "Calcula 25 * 4" or "125 * 8"
        math_match = re.search(
            r"\b(?:calcula|cuanto\s+es|\=\s*)?\s*([\d\s\+\-\*\/\(\)\.]+)\b",
            text_clean,
            re.IGNORECASE,
        )
        if math_match:
            cand = math_match.group(1).strip()
            if any(op in cand for op in ("+", "-", "*", "/")):
                return "calculator_tool", {"expression": cand}, None

        # Contextual Date/Time Continuation ("¿Y qué día es?", "¿Y qué hora?")
        if re.search(r"\b(?:qu[eé]\s+d[ií]a\s+es|qu[eé]\s+d[ií]a)\b", text_clean, re.IGNORECASE):
            return "datetime_tool", {"action": "day"}, "day"
        if re.search(r"\b(?:qu[eé]\s+hora\s+es|qu[eé]\s+hora)\b", text_clean, re.IGNORECASE):
            return "datetime_tool", {"action": "time"}, "time"
        if re.search(
            r"\b(?:qu[eé]\s+fecha\s+es|fecha\s+y\s+hora|fecha)\b",
            text_clean,
            re.IGNORECASE,
        ):
            return "datetime_tool", {"action": "now"}, "now"

        # Previous result reference ("¿Cuál fue el resultado anterior?", "Repite eso")
        if re.search(
            r"\b(?:resultado\s+anterior|anterior|que\s+dijiste)\b",
            text_clean,
            re.IGNORECASE,
        ):
            if last_action_id and self.tool_registry.get(last_action_id):
                return last_action_id, {}, None
            return "datetime_tool", {"action": "now"}, None

        # System observation queries ("métricas del sistema", "cpu", "memoria", "observación")
        if re.search(
            r"\b(?:m[eé]tricas|uso\s+de\s+cpu|memoria\s+disponible|disco|rendimiento)\b",
            text_clean,
            re.IGNORECASE,
        ):
            return "real_system_observation_tool", {"action": "all"}, None

        # Sandboxed file queries
        file_write_match = re.search(
            r"\b(?:escribe|guarda|crea)\s+archivo\s+([^\s]+)\s+con\s+(.+)\b",
            text_clean,
            re.IGNORECASE,
        )
        if file_write_match:
            f_path, f_content = file_write_match.group(1), file_write_match.group(2)
            return (
                "real_sandboxed_file_tool",
                {"action": "write", "path": f_path, "content": f_content},
                f_path,
            )

        file_read_match = re.search(
            r"\b(?:lee|muestra|consulta)\s+archivo\s+([^\s]+)\b",
            text_clean,
            re.IGNORECASE,
        )
        if file_read_match:
            f_path = file_read_match.group(1)
            return "real_sandboxed_file_tool", {"action": "read", "path": f_path}, f_path

        # HTTP retrieval queries
        http_match = re.search(
            r"\b(?:consulta|obt[eé]n|descarga|fetch)\s+(https?://[^\s]+)\b",
            text_clean,
            re.IGNORECASE,
        )
        if http_match:
            target_url = http_match.group(1)
            return "real_http_retrieval_tool", {"url": target_url, "method": "GET"}, target_url

        # System status query
        if re.search(
            r"\b(?:estado\s+del\s+sistema|status|salud|health)\b",
            text_clean,
            re.IGNORECASE,
        ):
            return "system_status_tool", {}, None

        # Default safe fallback tool proposal
        return "datetime_tool", {"action": "now"}, None

    def _generate_natural_response(
        self,
        operation: RuntimeOperation,
        tool_name: str,
        tool_output: Any,
        user_input: str,
    ) -> str:
        """Constructs a clear, natural response grounded strictly in real execution results."""
        if operation.state == RuntimeOperationState.BLOCKED:
            if operation.assurance_status == AssuranceStatus.SAFE_MODE.value:
                return (
                    "AURA está en modo seguro y no puede ejecutar nuevas operaciones en este"
                    " momento."
                )
            if (
                "governance" in (operation.failure_reason or "").lower()
                or "authority" in (operation.failure_reason or "").lower()
            ):
                return (
                    "No tengo autorización para realizar esa acción bajo el ámbito actual de"
                    " gobernanza."
                )
            return "No puedo realizar esa operación bajo la política actual."

        if operation.state == RuntimeOperationState.FAILED:
            err_detail = operation.failure_reason or "Error desconocido"
            return (
                f"No pude completar esa operación porque la herramienta produjo un error:"
                f" {err_detail}."
            )

        if operation.state != RuntimeOperationState.COMPLETED:
            return f"La operación se encuentra en estado '{operation.state.value}'."

        # Grounded response formatting for COMPLETED operations
        if tool_name == "calculator_tool":
            return f"El resultado es {tool_output}."

        if tool_name == "datetime_tool":
            if isinstance(tool_output, dict):
                formatted = tool_output.get("datetime_formatted", "")
                date_val = tool_output.get("date", "")
                time_val = tool_output.get("time", "")
                day_val = tool_output.get("day_of_week", "")
                return f"Hoy es {day_val}, {date_val} y la hora actual es {time_val} ({formatted})."
            elif isinstance(tool_output, str):
                if re.match(r"^\d{4}-\d{2}-\d{2}$", tool_output):
                    return f"La fecha actual me dice que es {tool_output}."
                elif re.match(r"^\d{2}:\d{2}:\d{2}$", tool_output):
                    return f"La hora actual es {tool_output}."
                else:
                    return f"Hoy es {tool_output}."
            return f"El resultado de la consulta de fecha/hora es: {tool_output}."

        if tool_name == "system_status_tool":
            return f"El estado del sistema AURA es óptimo: {tool_output}."

        if tool_name == "real_system_observation_tool":
            return f"Métricas del sistema observadas: {tool_output}."

        if tool_name == "real_sandboxed_file_tool":
            return f"Operación de archivo en sandbox completada: {tool_output}."

        if tool_name == "real_http_retrieval_tool":
            return f"Consulta HTTP recuperada exitosamente: {tool_output}."

        return f"Operación '{tool_name}' completada exitosamente. Resultado: {tool_output}."
