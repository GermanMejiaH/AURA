from __future__ import annotations

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import EventBus
from ..logging import get_logger
from ..modules.base import BaseModule
from ..world import CognitiveWorldModel
from .action_coordinator import ActionCoordinator
from .attention import AttentionManager
from .decision import DecisionEngine
from .planner import Planner
from .provider import LLMProvider, MockLLMProvider
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
    ) -> None:
        super().__init__(config, container, event_bus)
        self.state_machine = (
            state_machine
            if state_machine is not None
            else CognitiveStateMachine(event_bus=event_bus)
        )
        self.attention = AttentionManager()
        self.working_memory = WorkingMemory()
        self.llm_provider: LLMProvider = MockLLMProvider()
        self.reasoning = ReasoningEngine(
            llm_provider=self.llm_provider,
            working_memory=self.working_memory,
        )
        self.decision = DecisionEngine()
        self.planner = Planner()
        self.coordinator = ActionCoordinator(event_bus=event_bus)

    def on_initialize(self) -> None:
        logger = get_logger("CognitionModule")
        self.state_machine.transition_to(CognitiveState.IDLE, reason="cognition_initialized")

        # Register IoC instances
        if self._container is not None:
            self._container.register(CognitiveStateMachine, instance=self.state_machine)
            self._container.register(AttentionManager, instance=self.attention)
            self._container.register(WorkingMemory, instance=self.working_memory)
            self._container.register(ReasoningEngine, instance=self.reasoning)
            self._container.register(DecisionEngine, instance=self.decision)
            self._container.register(Planner, instance=self.planner)
            self._container.register(ActionCoordinator, instance=self.coordinator)

            # Connect CWM if available in container
            if self._container.has(CognitiveWorldModel):
                self.reasoning.cwm = self._container.resolve(CognitiveWorldModel)

        logger.info(f"CognitionModule initialized [state={self.state_machine.state.value}]")

    def process_cognitive_cycle(self, input_text: str, source: str = "user") -> ReasoningResult:
        """Runs full cognitive cycle: Attention -> Memory -> Reasoning -> Plan -> Action."""
        logger = get_logger("CognitionModule")
        self.state_machine.transition_to(CognitiveState.THINKING, reason="processing_cycle")

        # 1. Attention evaluation
        att_item = self.attention.evaluate_event("UserRequest", {"text": input_text}, source=source)
        if att_item:
            logger.debug(f"Attention focused on: {att_item.target} (priority={att_item.priority})")

        # 2. Working Memory update
        self.working_memory.add_conversation_turn("user", input_text)

        # 3. Reasoning
        reasoning_res = self.reasoning.analyze(input_text)

        # 4. Decision
        decision_obj = self.decision.evaluate(reasoning_res)

        # 5. Planning
        plan = self.planner.create_plan(decision_obj)

        # 6. Action Execution
        self.state_machine.transition_to(CognitiveState.EXECUTING, reason="executing_plan")
        self.coordinator.execute_plan(plan)

        # 7. Complete cycle -> IDLE
        self.working_memory.add_conversation_turn("assistant", reasoning_res.summary)
        self.state_machine.transition_to(CognitiveState.IDLE, reason="cycle_complete")

        return reasoning_res
