from __future__ import annotations

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import Event, EventBus
from ..logging import get_logger
from ..modules.base import BaseModule
from .goals import GoalManager
from .learning import LearningEngine
from .planning import LongHorizonPlanner
from .prioritization import PriorityEngine


class AutonomyModule(BaseModule):
    """Core module managing autonomous goal prioritization, planning & continuous learning."""

    name = "autonomy"
    description = "Autonomy System - Goal Tracking, Long-Horizon Planning & Learning"
    priority = 60

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        container: DependencyContainer | None = None,
        event_bus: EventBus | None = None,
        goal_manager: GoalManager | None = None,
        priority_engine: PriorityEngine | None = None,
        planner: LongHorizonPlanner | None = None,
        learning_engine: LearningEngine | None = None,
    ) -> None:
        super().__init__(config, container, event_bus)
        self.goals = goal_manager or GoalManager(event_bus=event_bus)
        self.priority_engine = priority_engine or PriorityEngine(event_bus=event_bus)
        self.planner = planner or LongHorizonPlanner(event_bus=event_bus)
        self.learning = learning_engine or LearningEngine(event_bus=event_bus)

    def on_initialize(self) -> None:
        logger = get_logger("AutonomyModule")

        # Register IoC instances
        if self._container is not None:
            self._container.register(GoalManager, instance=self.goals)
            self._container.register(PriorityEngine, instance=self.priority_engine)
            self._container.register(LongHorizonPlanner, instance=self.planner)
            self._container.register(LearningEngine, instance=self.learning)

        # Event Subscriptions
        self.subscribe("GoalSet", self._on_goal_set)
        self.subscribe("GoalAchieved", self._on_goal_achieved)

        logger.info("AutonomyModule initialized")

    def _on_goal_set(self, event: Event) -> None:
        desc = getattr(event, "description", "") or event.payload.get("description", "Goal")
        goal = self.goals.create_goal(description=desc)
        self.goals.update_status(goal.goal_id, "active")
        self.planner.generate_plan(goal)
        active = self.goals.get_active_goals()
        self.priority_engine.rank_goals(active)

    def _on_goal_achieved(self, event: Event) -> None:
        goal_id = getattr(event, "goal_id", "") or event.payload.get("goal_id", "")
        if goal_id:
            self.goals.update_status(goal_id, "achieved")
            self.learning.record_feedback(goal_id, success=True)
