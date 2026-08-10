from __future__ import annotations

import time

from ..autonomy.agent_models import TaskStatus
from ..autonomy.planner import AgentPlanner
from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import EventBus
from ..logging import get_logger
from ..memory import AgentPlanStore
from ..modules.base import BaseModule
from ..tools.registry import ToolRegistry
from ..world import CognitiveWorldModel
from .action_coordinator import ActionCoordinator
from .attention import AttentionManager
from .context import CognitiveContextBuilder
from .decision import DecisionEngine
from .factory import create_llm_provider
from .identity import IdentityManager
from .intent import Intent, IntentDetector, IntentType
from .planner import Planner
from .provider import LLMProvider
from .reasoning import ReasoningEngine, ReasoningResult
from .session import SessionManager
from .states import CognitiveState, CognitiveStateMachine
from .working_memory import WorkingMemory


class CognitionModule(BaseModule):
    """Core module orchestrating AURA's cognitive cycle (SPEC-001 & ADR-002)."""

    name = "cognition"
    description = "Cognitive Engine - State Machine, Attention, Reasoning, Decision & Planning"
    priority = 20

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        container: DependencyContainer | None = None,
        event_bus: EventBus | None = None,
        state_machine: CognitiveStateMachine | None = None,
        llm_provider: LLMProvider | None = None,
        plan_store: AgentPlanStore | None = None,
    ) -> None:
        super().__init__(config, container, event_bus)
        self.state_machine = (
            state_machine
            if state_machine is not None
            else CognitiveStateMachine(event_bus=event_bus)
        )
        self.attention = AttentionManager()
        self.working_memory = WorkingMemory()
        self.identity_manager = IdentityManager(config=config)
        self.session_manager = SessionManager(event_bus=event_bus)
        self.intent_detector = IntentDetector()
        self.llm_provider: LLMProvider = (
            llm_provider
            if llm_provider is not None
            else create_llm_provider(config=config, container=container)
        )
        self.reasoning = ReasoningEngine(
            llm_provider=self.llm_provider,
            working_memory=self.working_memory,
        )
        self.decision = DecisionEngine()
        self.planner = Planner()
        self.coordinator = ActionCoordinator(event_bus=event_bus)
        self.context_builder = CognitiveContextBuilder(container=container)
        self.plan_store = plan_store if plan_store is not None else AgentPlanStore()
        from .tool_orchestrator import ToolOrchestrator

        self.tool_orchestrator = ToolOrchestrator(event_bus=event_bus)

    def on_initialize(self) -> None:
        logger = get_logger("CognitionModule")
        self.state_machine.transition_to(CognitiveState.IDLE, reason="cognition_initialized")

        # Register IoC instances
        if self._container is not None:
            self._container.register(CognitiveStateMachine, instance=self.state_machine)
            self._container.register(AttentionManager, instance=self.attention)
            self._container.register(WorkingMemory, instance=self.working_memory)
            self._container.register(IdentityManager, instance=self.identity_manager)
            self._container.register(SessionManager, instance=self.session_manager)
            self._container.register(IntentDetector, instance=self.intent_detector)
            self._container.register(LLMProvider, instance=self.llm_provider)
            self._container.register(ReasoningEngine, instance=self.reasoning)
            self._container.register(DecisionEngine, instance=self.decision)
            self._container.register(Planner, instance=self.planner)
            self._container.register(ActionCoordinator, instance=self.coordinator)
            self._container.register(AgentPlanStore, instance=self.plan_store)
            from .tool_orchestrator import ToolOrchestrator

            self._container.register(ToolOrchestrator, instance=self.tool_orchestrator)

            # Update context builder container reference
            self.context_builder.container = self._container

            # Connect CWM if available in container
            if self._container.has(CognitiveWorldModel):
                self.reasoning.cwm = self._container.resolve(CognitiveWorldModel)

        logger.info(
            f"CognitionModule initialized [state={self.state_machine.state.value}, "
            f"llm={type(self.llm_provider).__name__}]"
        )

    @staticmethod
    def _is_agentic_request(input_text: str, intent: Intent) -> bool:
        clean = input_text.strip().lower()
        if clean.startswith(
            (
                "planifica",
                "crea un plan",
                "ejecuta el plan",
                "organiza",
                "busca y",
                "analiza y",
                "revisa y",
            )
        ):
            return True
        return intent.intent_type == IntentType.TASK_REQUEST and (
            " y " in clean or "para " in clean or len(clean.split()) >= 5
        )

    def process_cognitive_cycle(self, input_text: str, source: str = "user") -> ReasoningResult:
        """Runs cognitive cycle: Attention -> Intent -> Agentic -> Memory -> Context -> Tools."""
        logger = get_logger("CognitionModule")
        t_cycle_start = time.perf_counter()
        self.state_machine.transition_to(CognitiveState.THINKING, reason="processing_cycle")

        # 0. Intent detection & Session update
        detected_intent = self.intent_detector.detect(input_text)
        self.session_manager.update_intent(detected_intent)

        if self._event_bus is not None:
            from ..events import IntentDetected

            intent_name = (
                detected_intent.intent_type.value
                if hasattr(detected_intent.intent_type, "value")
                else str(detected_intent.intent_type)
            )
            self._event_bus.publish(
                IntentDetected(
                    source="CognitionModule",
                    intent_type=intent_name,
                    confidence=detected_intent.confidence,
                    raw_text=input_text,
                )
            )

        # --- AURA 1.1 STAGE 3 AGENTIC ROUTING & PERSISTENT CONFIRMATION FLOW ---
        from ..autonomy.executor import AgentExecutor

        active_plans = self.plan_store.list_active_plans()
        pending_plan = next((p for p in active_plans if p.is_waiting_confirmation()), None)

        if pending_plan:
            waiting_task = next(
                (t for t in pending_plan.tasks if t.status == TaskStatus.WAITING_CONFIRMATION),
                None,
            )

            # User Confirmation Flow
            if detected_intent.intent_type == IntentType.CONFIRMATION:
                if waiting_task:
                    tool_reg = (
                        self._container.resolve(ToolRegistry)
                        if self._container and self._container.has(ToolRegistry)
                        else None
                    )
                    from ..autonomy.replanner import AgentReplanner

                    agent_replanner = AgentReplanner(llm_provider=self.llm_provider)
                    executor = AgentExecutor(
                        event_bus=self._event_bus,
                        registry=tool_reg,
                        replanner=agent_replanner,
                        plan_store=self.plan_store,
                    )
                    executor.authorize_task(pending_plan, waiting_task.task_id)
                    res = executor.resume_plan(pending_plan, registry=tool_reg)
                    self.plan_store.update_plan(pending_plan)

                    if res.waiting_confirmation:
                        new_waiting = next(
                            (
                                t
                                for t in pending_plan.tasks
                                if t.status == TaskStatus.WAITING_CONFIRMATION
                            ),
                            None,
                        )
                        new_tool = new_waiting.tool_name if new_waiting else "herramienta"
                        new_desc = new_waiting.description if new_waiting else ""
                        summary = (
                            f"Tarea '{waiting_task.description}' autorizada y ejecutada. "
                            f"La siguiente tarea '{new_desc}' requiere confirmación para "
                            f"usar '{new_tool}'. ¿Deseas autorizar esta acción?"
                        )
                        sess_ctx = self.session_manager.get_context()
                        sess_ctx.active_task = "WAITING_FOR_CONFIRMATION"
                    elif res.completed:
                        summary = (
                            f"Confirmación recibida. Plan completado con éxito: "
                            f"{waiting_task.result or 'Ejecutado'}"
                        )
                    else:
                        failed_t = next(
                            (t for t in pending_plan.tasks if t.status == TaskStatus.FAILED),
                            None,
                        )
                        err_msg = failed_t.error if failed_t else "Error en la ejecución."
                        summary = f"Confirmación recibida, pero ocurrió un problema: {err_msg}"

                    self.working_memory.add_conversation_turn("user", input_text)
                    self.working_memory.add_conversation_turn("assistant", summary)
                    self.session_manager.record_turn()
                    self.state_machine.transition_to(
                        CognitiveState.IDLE, reason="agent_resume_complete"
                    )
                    return ReasoningResult(
                        summary=summary,
                        intent="agent_resume",
                        confidence=1.0,
                    )

            # User Cancellation Flow
            if detected_intent.intent_type == IntentType.CANCELLATION:
                if waiting_task:
                    executor = AgentExecutor(event_bus=self._event_bus)
                    executor.deny_task(
                        pending_plan,
                        waiting_task.task_id,
                        reason="Cancelado por el usuario",
                    )
                    self.plan_store.update_plan(pending_plan)
                    summary = f"Entendido, la tarea '{waiting_task.description}' ha sido cancelada."

                    self.working_memory.add_conversation_turn("user", input_text)
                    self.working_memory.add_conversation_turn("assistant", summary)
                    self.session_manager.record_turn()
                    self.state_machine.transition_to(
                        CognitiveState.IDLE, reason="agent_cancel_complete"
                    )
                    return ReasoningResult(
                        summary=summary,
                        intent="agent_cancel",
                        confidence=1.0,
                    )

        # Check for new Agentic Multi-Step Goal
        if self._is_agentic_request(input_text, detected_intent):
            tool_reg = (
                self._container.resolve(ToolRegistry)
                if self._container and self._container.has(ToolRegistry)
                else None
            )
            agent_planner = AgentPlanner(llm_provider=self.llm_provider, registry=tool_reg)
            from ..autonomy.replanner import AgentReplanner

            agent_replanner = AgentReplanner(llm_provider=self.llm_provider)
            try:
                agent_plan = agent_planner.create_plan(input_text)
                # PERSIST PLAN BEFORE EXECUTION
                self.plan_store.save_plan(agent_plan)

                # EXECUTE PLAN
                executor = AgentExecutor(
                    event_bus=self._event_bus,
                    registry=tool_reg,
                    replanner=agent_replanner,
                    plan_store=self.plan_store,
                )
                self.state_machine.transition_to(
                    CognitiveState.EXECUTING, reason="executing_agent_plan"
                )
                res = executor.execute_plan(agent_plan, registry=tool_reg)

                # UPDATE PERSISTED PLAN STATE
                self.plan_store.update_plan(agent_plan)

                if res.waiting_confirmation:
                    waiting_task = next(
                        (
                            t
                            for t in agent_plan.tasks
                            if t.status == TaskStatus.WAITING_CONFIRMATION
                        ),
                        None,
                    )
                    tool_name = waiting_task.tool_name if waiting_task else "accion"
                    desc = waiting_task.description if waiting_task else ""
                    summary = (
                        f"Para realizar '{desc}', necesito tu confirmación para ejecutar "
                        f"la herramienta '{tool_name}'. ¿Deseas autorizar esta acción?"
                    )
                    sess_ctx = self.session_manager.get_context()
                    sess_ctx.active_task = "WAITING_FOR_CONFIRMATION"
                elif res.completed:
                    task_summaries = [
                        f"- {t.description}: {t.result}" for t in agent_plan.tasks if t.result
                    ]
                    details = (
                        "\n".join(task_summaries)
                        if task_summaries
                        else "Todas las tareas fueron completadas."
                    )
                    summary = f"Plan completado con éxito:\n{details}"
                else:
                    failed_task = next(
                        (t for t in agent_plan.tasks if t.status == TaskStatus.FAILED), None
                    )
                    err_msg = failed_task.error if failed_task else "Error en la ejecución."
                    summary = f"No fue posible completar el plan debido a un error: {err_msg}"

                self.working_memory.add_conversation_turn("user", input_text)
                self.working_memory.add_conversation_turn("assistant", summary)
                self.session_manager.record_turn()
                self.state_machine.transition_to(CognitiveState.IDLE, reason="agent_plan_complete")

                return ReasoningResult(
                    summary=summary,
                    intent="agent_plan",
                    confidence=1.0,
                )
            except Exception as exc:
                logger.warning(
                    f"AgentPlanner failed or non-agentic request: {exc}. "
                    "Falling back to standard reactive cycle."
                )

        # --- STANDARD REACTIVE MONO-TURNO FLOW ---
        # 1. Attention evaluation & Memory Directive check
        att_item = self.attention.evaluate_event("UserRequest", {"text": input_text}, source=source)
        if att_item:
            logger.debug(f"Attention focused on: {att_item.target} (priority={att_item.priority})")

        from .memory_detector import ExplicitMemoryDetector

        mem_directive = ExplicitMemoryDetector.detect(input_text)
        if mem_directive.detected and self._container is not None:
            from ..memory import Fact, MemoryModule

            if self._container.has(MemoryModule):
                mem_mod = self._container.resolve(MemoryModule)
                mem_mod.semantic.add_fact(
                    Fact(
                        subject=mem_directive.subject,
                        predicate=mem_directive.predicate,
                        object_val=mem_directive.object_val,
                        source="user",
                    )
                )
                mem_mod.preferences.set_preference(
                    mem_directive.predicate, mem_directive.object_val
                )
                logger.info(
                    f"Explicit memory stored: {mem_directive.subject} "
                    f"{mem_directive.predicate}={mem_directive.object_val}"
                )

        # 2. Build Cognitive Context
        t0 = time.perf_counter()
        default_identity = CognitiveContextBuilder.DEFAULT_INSTRUCTION
        system_identity = (
            self._config.get_typed("llm.system_identity", str, default_identity)
            if self._config is not None
            else default_identity
        )

        # 2.0 Build Conversation Context (Step 4: Anaphora resolution & Smart filtering)
        from .conversation_context import (
            AnaphoraResolver,
            ConversationContext,
            ConversationContextFilter,
        )

        history_turns = self.working_memory.get_recent_conversation(limit=12)
        sess_ctx = self.session_manager.get_context()

        recent_entities: list[str] = []
        if sess_ctx.active_entity:
            recent_entities.append(sess_ctx.active_entity)

        anaphora_res = AnaphoraResolver.analyze(
            user_input=input_text,
            recent_entities=recent_entities,
            active_topic=sess_ctx.current_topic,
            active_entity=sess_ctx.active_entity,
        )

        relevant_turns = ConversationContextFilter.filter_turns(
            history=history_turns,
            current_topic=sess_ctx.current_topic,
            active_task=sess_ctx.active_task,
            task_detail=sess_ctx.task_detail,
            active_entity=sess_ctx.active_entity,
            anaphora_resolution=anaphora_res,
            max_turns=8,
        )

        conv_ctx = ConversationContext(
            active_topic=sess_ctx.current_topic,
            active_task=sess_ctx.active_task,
            task_detail=sess_ctx.task_detail,
            active_entity=sess_ctx.active_entity,
            relevant_turns=relevant_turns,
            anaphora_resolution=anaphora_res,
        )

        cognitive_context = self.context_builder.build(
            input_text=input_text,
            system_instruction=system_identity,
            working_memory=self.working_memory,
            conversation_context=conv_ctx,
        )
        t_context_build = time.perf_counter() - t0

        # 2.1 Tool Orchestration (Tool Use & Action Orchestration)
        if self._container is not None:
            if self._container.has(ToolRegistry):
                tool_reg = self._container.resolve(ToolRegistry)
                tool_results = self.tool_orchestrator.orchestrate(
                    input_text=input_text,
                    intent=detected_intent,
                    registry=tool_reg,
                )
                if tool_results:
                    cognitive_context.tool_results = tool_results
                    if any(tr.get("requires_confirmation") for tr in tool_results):
                        sess_ctx = self.session_manager.get_context()
                        sess_ctx.active_task = "WAITING_FOR_CONFIRMATION"

        # 3. Reasoning via LLM Provider
        t0 = time.perf_counter()
        if mem_directive.detected:
            reasoning_res = ReasoningResult(
                summary=mem_directive.confirmation_response,
                intent="store_memory",
                confidence=1.0,
            )
        else:
            reasoning_res = self.reasoning.analyze(input_text, cognitive_context=cognitive_context)
        t_llm_request = time.perf_counter() - t0

        # 4. Decision
        decision_obj = self.decision.evaluate(reasoning_res)

        # 5. Planning
        plan = self.planner.create_plan(decision_obj)

        # 6. Action Execution
        self.state_machine.transition_to(CognitiveState.EXECUTING, reason="executing_plan")
        self.coordinator.execute_plan(plan)

        # 7. Complete cycle -> Working Memory update, Session turn increment & IDLE
        self.working_memory.add_conversation_turn("user", input_text)
        self.working_memory.add_conversation_turn("assistant", reasoning_res.summary)
        self.session_manager.record_turn()
        self.state_machine.transition_to(CognitiveState.IDLE, reason="cycle_complete")

        t_total = time.perf_counter() - t_cycle_start
        logger.info(
            f"Cognitive cycle complete: context_build={t_context_build:.3f}s "
            f"llm_request={t_llm_request:.3f}s total={t_total:.3f}s"
        )

        return reasoning_res
