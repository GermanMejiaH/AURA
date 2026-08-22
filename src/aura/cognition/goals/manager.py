from typing import Any

from aura.cognition.deliberation.models import RiskLevel
from aura.events.bus import EventBus
from aura.events.models import (
    GoalOutcomeRecorded,
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
        container: Any | None = None,
    ) -> None:
        self.store = store if store is not None else GoalStore(container=container)
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

    def record_execution_outcome(
        self,
        goal_id: str,
        plan: Any | None = None,
        result: Any | None = None,
        status: GoalStatus | str | None = None,
        progress_percentage: float | None = None,
        reason: str = "",
    ) -> PersistentGoal | None:
        """Deterministically records execution outcome of an AgentPlan run on PersistentGoal."""
        goal = self.store.get_goal(goal_id)
        if not goal:
            logger.warning(
                f"PersistentGoal '{goal_id}' not found when recording execution outcome."
            )
            return None

        # Terminal state idempotency check: do not overwrite terminal state unless explicitly forced
        terminal_statuses = {GoalStatus.COMPLETED, GoalStatus.CANCELLED}
        if goal.status in terminal_statuses:
            logger.info(
                f"PersistentGoal '{goal_id}' is already in terminal state '{goal.status.value}'. "
                "Outcome recording skipped."
            )
            return goal

        # Determine target status and progress from plan/result or explicit parameters
        target_status = goal.status
        target_progress = goal.progress.completion_percentage

        if status is not None:
            target_status = GoalStatus(status) if isinstance(status, str) else status
        elif result is not None or plan is not None:
            is_completed = getattr(result, "completed", False) or (
                plan.is_completed() if plan else False
            )
            is_failed = getattr(result, "failed", False) or (plan.is_failed() if plan else False)
            is_waiting = getattr(result, "waiting_confirmation", False) or (
                plan.is_waiting_confirmation() if plan else False
            )

            if is_completed:
                target_status = GoalStatus.COMPLETED
                target_progress = 100.0
            elif is_failed:
                target_status = GoalStatus.FAILED
            elif is_waiting:
                target_status = GoalStatus.BLOCKED
            elif plan and plan.tasks:
                succeeded_tasks = sum(1 for t in plan.tasks if t.status.value == "SUCCESS")
                total_tasks = len(plan.tasks)
                if total_tasks > 0:
                    calculated = round((succeeded_tasks / total_tasks) * 100.0, 1)
                    target_progress = max(target_progress, calculated)
                if target_progress >= 100.0:
                    target_status = GoalStatus.COMPLETED
                else:
                    target_status = GoalStatus.ACTIVE

        if progress_percentage is not None:
            target_progress = max(0.0, min(100.0, float(progress_percentage)))
            if target_progress >= 100.0 and target_status != GoalStatus.CANCELLED:
                target_status = GoalStatus.COMPLETED

        # Update progress and status safely
        self.update_progress(goal_id, percentage=target_progress, notes=reason)
        if goal.status != target_status:
            self.set_status(goal_id, target_status)

        updated_goal = self.store.get_goal(goal_id)

        if self.event_bus and updated_goal:
            plan_id = getattr(plan, "plan_id", "") if plan else getattr(result, "plan_id", "")
            strat_id = getattr(plan, "strategy_id", None) if plan else None
            self.event_bus.publish(
                GoalOutcomeRecorded(
                    goal_id=updated_goal.goal_id,
                    plan_id=plan_id,
                    status=updated_goal.status.value,
                    completion_percentage=updated_goal.progress.completion_percentage,
                    strategy_id=strat_id,
                    reason=reason
                    or f"Execution recorded with outcome '{updated_goal.status.value}'",
                )
            )

        return updated_goal
