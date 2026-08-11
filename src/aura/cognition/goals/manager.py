from aura.cognition.deliberation.models import RiskLevel
from aura.events.bus import EventBus
from aura.events.models import (
    GoalProgressUpdated,
    GoalStatusChanged,
    GoalUpdated,
    PersistentGoalCreated,
)
from aura.logging import get_logger

from .models import (
    GoalContextRef,
    GoalPriority,
    GoalStatus,
    PersistentGoal,
)
from .store import GoalStore

logger = get_logger("GoalManager")


class GoalManager:
    """Domain service managing lifecycle and events for PersistentGoals."""

    def __init__(
        self,
        store: GoalStore | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.store = store if store is not None else GoalStore()
        self.event_bus = event_bus

    def create_goal(
        self,
        description: str,
        priority: GoalPriority = GoalPriority.MEDIUM,
        constraints: list[str] | None = None,
        success_criteria: list[str] | None = None,
        context: GoalContextRef | None = None,
        parent_goal_id: str | None = None,
        risk_tolerance: RiskLevel = RiskLevel.MEDIUM,
    ) -> PersistentGoal:
        """Creates, persists, and publishes a new PersistentGoal."""
        if not description or not description.strip():
            raise ValueError("PersistentGoal description cannot be empty.")

        goal = PersistentGoal(
            description=description.strip(),
            priority=priority,
            status=GoalStatus.PENDING,
            constraints=constraints or [],
            success_criteria=success_criteria or [],
            context=context or GoalContextRef(),
            parent_goal_id=parent_goal_id,
            risk_tolerance=risk_tolerance,
        )

        self.store.save_goal(goal)
        logger.info(f"Created PersistentGoal '{goal.goal_id}': '{goal.description}'")

        if self.event_bus:
            self.event_bus.publish(
                PersistentGoalCreated(
                    goal_id=goal.goal_id,
                    description=goal.description,
                    priority=goal.priority.value,
                    status=goal.status.value,
                )
            )

        return goal

    def get_goal(self, goal_id: str) -> PersistentGoal | None:
        """Retrieves a PersistentGoal by ID."""
        return self.store.get_goal(goal_id)

    def list_goals(
        self,
        status: GoalStatus | str | None = None,
        priority: GoalPriority | str | None = None,
        parent_goal_id: str | None = None,
    ) -> list[PersistentGoal]:
        """Lists PersistentGoals filtered by status, priority, or parent_goal_id."""
        return self.store.list_goals(
            status=status, priority=priority, parent_goal_id=parent_goal_id
        )

    def update_goal(
        self,
        goal_id: str,
        description: str | None = None,
        priority: GoalPriority | None = None,
        constraints: list[str] | None = None,
        success_criteria: list[str] | None = None,
        risk_tolerance: RiskLevel | None = None,
    ) -> PersistentGoal:
        """Updates fields of an existing PersistentGoal and publishes GoalUpdated event."""
        goal = self.store.get_goal(goal_id)
        if not goal:
            raise ValueError(f"PersistentGoal with ID '{goal_id}' not found.")

        updated_fields: list[str] = []

        if description is not None and description.strip():
            goal.description = description.strip()
            updated_fields.append("description")

        if priority is not None:
            goal.priority = priority
            updated_fields.append("priority")

        if constraints is not None:
            goal.constraints = list(constraints)
            updated_fields.append("constraints")

        if success_criteria is not None:
            goal.success_criteria = list(success_criteria)
            updated_fields.append("success_criteria")

        if risk_tolerance is not None:
            goal.risk_tolerance = risk_tolerance
            updated_fields.append("risk_tolerance")

        if updated_fields:
            goal.set_status(goal.status)  # Updates updated_at timestamp
            self.store.save_goal(goal)

            if self.event_bus:
                self.event_bus.publish(
                    GoalUpdated(
                        goal_id=goal.goal_id,
                        updated_fields=updated_fields,
                    )
                )

        return goal

    def set_status(self, goal_id: str, status: GoalStatus) -> PersistentGoal:
        """Changes the status of a PersistentGoal and publishes GoalStatusChanged event."""
        goal = self.store.get_goal(goal_id)
        if not goal:
            raise ValueError(f"PersistentGoal with ID '{goal_id}' not found.")

        old_status = goal.status
        if old_status != status:
            goal.set_status(status)
            self.store.save_goal(goal)

            if self.event_bus:
                self.event_bus.publish(
                    GoalStatusChanged(
                        goal_id=goal.goal_id,
                        old_status=old_status.value,
                        new_status=status.value,
                    )
                )

        return goal

    def update_progress(
        self,
        goal_id: str,
        percentage: float | None = None,
        add_milestone: str | None = None,
        notes: str | None = None,
    ) -> PersistentGoal:
        """Updates progress of a PersistentGoal and publishes GoalProgressUpdated event."""
        goal = self.store.get_goal(goal_id)
        if not goal:
            raise ValueError(f"PersistentGoal with ID '{goal_id}' not found.")

        goal.progress.update(percentage=percentage, add_milestone=add_milestone, notes=notes)
        goal.set_status(goal.status)
        self.store.save_goal(goal)

        if self.event_bus:
            self.event_bus.publish(
                GoalProgressUpdated(
                    goal_id=goal.goal_id,
                    completion_percentage=goal.progress.completion_percentage,
                    milestone_added=add_milestone,
                )
            )

        return goal

    def cancel_goal(self, goal_id: str) -> PersistentGoal:
        """Logically cancels a PersistentGoal by setting its status to CANCELLED."""
        return self.set_status(goal_id, GoalStatus.CANCELLED)

    def delete_goal(self, goal_id: str) -> bool:
        """Physically deletes a PersistentGoal from the database."""
        return self.store.delete_goal(goal_id)
