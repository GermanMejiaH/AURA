from __future__ import annotations

import time

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import EventBus
from ..logging import get_logger
from ..modules.base import BaseModule
from ..world import CognitiveWorldModel
from .action_coordinator import ActionCoordinator
from .attention import AttentionManager
from .context import CognitiveContextBuilder
from .decision import DecisionEngine
from .factory import create_llm_provider
from .planner import Planner
from .provider import LLMProvider
from .reasoning import ReasoningEngine, ReasoningResult
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
    ) -> None:
        super().__init__(config, container, event_bus)
        self.state_machine = (
            state_machine
            if state_machine is not None
            else CognitiveStateMachine(event_bus=event_bus)
        )
        self.attention = AttentionManager()
        self.working_memory = WorkingMemory()
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

    def on_initialize(self) -> None:
        logger = get_logger("CognitionModule")
        self.state_machine.transition_to(CognitiveState.IDLE, reason="cognition_initialized")

        # Register IoC instances
        if self._container is not None:
            self._container.register(CognitiveStateMachine, instance=self.state_machine)
            self._container.register(AttentionManager, instance=self.attention)
            self._container.register(WorkingMemory, instance=self.working_memory)
            self._container.register(LLMProvider, instance=self.llm_provider)
            self._container.register(ReasoningEngine, instance=self.reasoning)
            self._container.register(DecisionEngine, instance=self.decision)
            self._container.register(Planner, instance=self.planner)
            self._container.register(ActionCoordinator, instance=self.coordinator)

            # Update context builder container reference
            self.context_builder.container = self._container

            # Connect CWM if available in container
            if self._container.has(CognitiveWorldModel):
                self.reasoning.cwm = self._container.resolve(CognitiveWorldModel)

        logger.info(
            f"CognitionModule initialized [state={self.state_machine.state.value}, "
            f"llm={type(self.llm_provider).__name__}]"
        )

    def process_cognitive_cycle(self, input_text: str, source: str = "user") -> ReasoningResult:
        """Runs cognitive cycle: Attention -> Memory -> Context -> Reasoning -> Action."""
        logger = get_logger("CognitionModule")
        t_cycle_start = time.perf_counter()
        self.state_machine.transition_to(CognitiveState.THINKING, reason="processing_cycle")

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
        default_identity = (
            "Eres AURA (Adaptive Unified Reasoning Assistant), asistente de voz en español. "
            "Respondes de forma natural, concisa y directa (1 a 3 oraciones)."
        )
        system_identity = (
            self._config.get_typed("llm.system_identity", str, default_identity)
            if self._config is not None
            else ""
        )
        cognitive_context = self.context_builder.build(
            input_text=input_text,
            system_instruction=system_identity,
            working_memory=self.working_memory,
        )
        t_context_build = time.perf_counter() - t0

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

        # 7. Complete cycle -> Working Memory update & IDLE
        self.working_memory.add_conversation_turn("user", input_text)
        self.working_memory.add_conversation_turn("assistant", reasoning_res.summary)
        self.state_machine.transition_to(CognitiveState.IDLE, reason="cycle_complete")

        t_total = time.perf_counter() - t_cycle_start
        logger.info(
            f"Cognitive cycle complete: context_build={t_context_build:.3f}s "
            f"llm_request={t_llm_request:.3f}s total={t_total:.3f}s"
        )

        return reasoning_res
