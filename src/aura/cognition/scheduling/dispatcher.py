from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from aura.cognition.goals import GoalManager, GoalStatus
from aura.events.bus import EventBus
from aura.events.models import (
    ScheduleRunRecorded,
    ScheduleSkipped,
    ScheduleTriggered,
)
from aura.logging import get_logger

from .evaluator import ScheduleEvaluator
from .models import ScheduleStatus, TemporalSchedule
from .store import ScheduleStore

if TYPE_CHECKING:
    from aura.autonomy.executor import AgentExecutor
    from aura.autonomy.planner import AgentPlanner
    from aura.tools.registry import ToolRegistry

    from .execution import RuntimeExecutionEngine
    from .governance import RuntimeGovernanceEngine
    from .resolution import RuntimePolicyEngine

logger = get_logger("ScheduleDispatcher")


@dataclass(frozen=True)
class DispatchResult:
    """Encapsulates the outcome of evaluating and dispatching a single TemporalSchedule."""

    schedule_id: str
    goal_id: str
    dispatched: bool
    status: ScheduleStatus
    iterations_count: int
    last_run_at: str | None
    next_run_at: str | None
    reason: str


class ScheduleDispatcher:
    """Synchronous service binding TemporalSchedules to PersistentGoal execution cycles."""

    def __init__(
        self,
        schedule_store: ScheduleStore,
        goal_manager: GoalManager,
        evaluator: ScheduleEvaluator | None = None,
        event_bus: EventBus | None = None,
        planner: AgentPlanner | None = None,
        executor: AgentExecutor | None = None,
        registry: ToolRegistry | None = None,
        governance_engine: RuntimeGovernanceEngine | None = None,
        policy_engine: RuntimePolicyEngine | None = None,
        execution_engine: RuntimeExecutionEngine | None = None,
    ) -> None:
        self.schedule_store = schedule_store
        self.goal_manager = goal_manager
        self.evaluator = evaluator or ScheduleEvaluator()
        self.event_bus = event_bus
        self.planner = planner
        self.executor = executor
        self.registry = registry
        self.governance_engine = governance_engine
        self.policy_engine = policy_engine
        self.execution_engine = execution_engine
        self._active_dispatches: set[str] = set()

    def process_due_schedules(
        self,
        at_timestamp: str | None = None,
        execute_goals: bool = True,
    ) -> list[DispatchResult]:
        """Evaluates and dispatches all due schedules at the given UTC ISO at_timestamp."""
        now_dt = datetime.now(UTC)
        now_iso = at_timestamp or now_dt.isoformat()

        candidates = self.schedule_store.list_eligible_schedules(at_timestamp=now_iso)
        results: list[DispatchResult] = []

        for sched in candidates:
            res = self._dispatch_single_schedule(
                sched, now_iso=now_iso, execute_goals=execute_goals
            )
            results.append(res)

        return results

    def _dispatch_single_schedule(
        self,
        sched: TemporalSchedule,
        now_iso: str,
        execute_goals: bool,
    ) -> DispatchResult:
        """Processes a single TemporalSchedule cleanly with deduplication and error recovery."""
        # 1. Deduplication check
        if sched.schedule_id in self._active_dispatches:
            reason = "Schedule is currently dispatching (deduplicated)"
            if self.event_bus:
                self.event_bus.publish(
                    ScheduleSkipped(
                        schedule_id=sched.schedule_id,
                        goal_id=sched.goal_id,
                        reason=reason,
                    )
                )
            return DispatchResult(
                schedule_id=sched.schedule_id,
                goal_id=sched.goal_id,
                dispatched=False,
                status=sched.status,
                iterations_count=sched.iterations_count,
                last_run_at=sched.last_run_at,
                next_run_at=sched.next_run_at,
                reason=reason,
            )

        self._active_dispatches.add(sched.schedule_id)
        execution_error: Exception | None = None
        try:
            # 2. Re-evaluate eligibility via ScheduleEvaluator
            eval_res = self.evaluator.evaluate_eligibility(sched, at_timestamp=now_iso)
            if not eval_res.is_eligible:
                reason = f"Schedule not eligible: {eval_res.reason}"
                if self.event_bus:
                    self.event_bus.publish(
                        ScheduleSkipped(
                            schedule_id=sched.schedule_id,
                            goal_id=sched.goal_id,
                            reason=reason,
                        )
                    )
                return DispatchResult(
                    schedule_id=sched.schedule_id,
                    goal_id=sched.goal_id,
                    dispatched=False,
                    status=sched.status,
                    iterations_count=sched.iterations_count,
                    last_run_at=sched.last_run_at,
                    next_run_at=sched.next_run_at,
                    reason=reason,
                )

            # 3. Target goal verification via GoalManager
            goal = self.goal_manager.get_goal(sched.goal_id)
            inactive_statuses = {
                GoalStatus.CANCELLED,
                GoalStatus.COMPLETED,
                GoalStatus.FAILED,
                GoalStatus.PAUSED,
            }
            if goal is None or goal.status in inactive_statuses:
                status_str = goal.status.value if goal else "MISSING"
                reason = f"Target goal missing or inactive (status: {status_str})"
                if self.event_bus:
                    self.event_bus.publish(
                        ScheduleSkipped(
                            schedule_id=sched.schedule_id,
                            goal_id=sched.goal_id,
                            reason=reason,
                        )
                    )
                return DispatchResult(
                    schedule_id=sched.schedule_id,
                    goal_id=sched.goal_id,
                    dispatched=False,
                    status=sched.status,
                    iterations_count=sched.iterations_count,
                    last_run_at=sched.last_run_at,
                    next_run_at=sched.next_run_at,
                    reason=reason,
                )

            # 3.4 Runtime Policy & Priority Evaluation
            if self.policy_engine is not None:
                pol_dec = self.policy_engine.evaluate_schedule(sched, goal=goal)
                if not pol_dec.allowed:
                    reason = (
                        f"Policy blocked/deferred execution: "
                        f"{pol_dec.action.value} ({pol_dec.reason})"
                    )
                    if self.event_bus:
                        self.event_bus.publish(
                            ScheduleSkipped(
                                schedule_id=sched.schedule_id,
                                goal_id=sched.goal_id,
                                reason=reason,
                            )
                        )
                    return DispatchResult(
                        schedule_id=sched.schedule_id,
                        goal_id=sched.goal_id,
                        dispatched=False,
                        status=sched.status,
                        iterations_count=sched.iterations_count,
                        last_run_at=sched.last_run_at,
                        next_run_at=sched.next_run_at,
                        reason=reason,
                    )

            # 3.5 Governance & Safeguard Evaluation
            if self.governance_engine is not None:
                gov_dec = self.governance_engine.evaluate_action(
                    action_id=sched.schedule_id,
                    is_mutating=True,
                    category="AUTONOMY",
                )
                if not gov_dec.allowed:
                    reason = f"Governance blocked execution: {gov_dec.reason}"
                    if self.event_bus:
                        self.event_bus.publish(
                            ScheduleSkipped(
                                schedule_id=sched.schedule_id,
                                goal_id=sched.goal_id,
                                reason=reason,
                            )
                        )
                    return DispatchResult(
                        schedule_id=sched.schedule_id,
                        goal_id=sched.goal_id,
                        dispatched=False,
                        status=sched.status,
                        iterations_count=sched.iterations_count,
                        last_run_at=sched.last_run_at,
                        next_run_at=sched.next_run_at,
                        reason=reason,
                    )

            # 4. Dry-run mode check
            if not execute_goals:
                reason = "Dry run / simulation mode"
                if self.event_bus:
                    self.event_bus.publish(
                        ScheduleSkipped(
                            schedule_id=sched.schedule_id,
                            goal_id=sched.goal_id,
                            reason=reason,
                        )
                    )
                return DispatchResult(
                    schedule_id=sched.schedule_id,
                    goal_id=sched.goal_id,
                    dispatched=False,
                    status=sched.status,
                    iterations_count=sched.iterations_count,
                    last_run_at=sched.last_run_at,
                    next_run_at=sched.next_run_at,
                    reason=reason,
                )

            # 5. Execute Goal Cycle & Bind Execution
            if self.event_bus:
                self.event_bus.publish(
                    ScheduleTriggered(
                        schedule_id=sched.schedule_id,
                        goal_id=sched.goal_id,
                        schedule_type=sched.schedule_type.value,
                        triggered_at=now_iso,
                    )
                )

            execution_error = None

            def _run_goal_cycle() -> Any:
                plan_inner: Any | None = None
                result_inner: Any | None = None
                goal_model = goal.to_goal_model()
                if self.planner:
                    try:
                        _, plan_inner = self.planner.deliberate_and_plan(goal_model)
                    except AttributeError:
                        plan_inner = self.planner.create_plan(goal_model)

                    if plan_inner and self.executor:
                        result_inner = self.executor.execute_plan(
                            plan_inner, registry=self.registry
                        )

                self.goal_manager.record_execution_outcome(
                    goal_id=goal.goal_id,
                    plan=plan_inner,
                    result=result_inner,
                    reason=f"Executed via TemporalSchedule '{sched.schedule_id}'",
                )
                return result_inner

            if self.execution_engine is not None:
                exec_res = self.execution_engine.execute_schedule_action(
                    sched=sched,
                    goal=goal,
                    goal_executor_fn=_run_goal_cycle,
                )
                if not exec_res.success:
                    execution_error = RuntimeError(
                        exec_res.error or "Transactional execution failed"
                    )
            else:
                try:
                    _run_goal_cycle()
                except Exception as exc:
                    execution_error = exc
                    logger.error(
                        f"Execution failed for goal '{goal.goal_id}' "
                        f"on schedule '{sched.schedule_id}': {exc}"
                    )
                    self.goal_manager.record_execution_outcome(
                        goal_id=goal.goal_id,
                        status=GoalStatus.FAILED,
                        reason=f"Schedule execution failed: {exc}",
                    )

            if self.governance_engine is not None:
                self.governance_engine.record_action_outcome(
                    action_id=sched.schedule_id,
                    success=(execution_error is None),
                    error=str(execution_error) if execution_error else None,
                )

            # 6. Record run and persist schedule update
            sched.record_run(run_at=now_iso, next_run_at=eval_res.calculated_next_run_at)
            self.schedule_store.save_schedule(sched)

            if self.event_bus:
                self.event_bus.publish(
                    ScheduleRunRecorded(
                        schedule_id=sched.schedule_id,
                        goal_id=sched.goal_id,
                        iterations_count=sched.iterations_count,
                        next_run_at=sched.next_run_at,
                        status=sched.status.value,
                    )
                )

            if execution_error:
                dispatch_reason = f"Execution error: {execution_error}"
                dispatched_flag = False
            else:
                dispatch_reason = "Goal execution dispatched successfully"
                dispatched_flag = True

            return DispatchResult(
                schedule_id=sched.schedule_id,
                goal_id=sched.goal_id,
                dispatched=dispatched_flag,
                status=sched.status,
                iterations_count=sched.iterations_count,
                last_run_at=sched.last_run_at,
                next_run_at=sched.next_run_at,
                reason=dispatch_reason,
            )
        finally:
            if self.policy_engine is not None:
                self.policy_engine.record_task_completion(
                    sched.schedule_id, success=(execution_error is None)
                )
            self._active_dispatches.discard(sched.schedule_id)
