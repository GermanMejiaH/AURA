from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..cognition.evaluator import EvaluationStatus, TaskEvaluator
from ..cognition.reflection import CognitiveReflector
from ..cognition.verification import ActionVerifier, VerificationStatus
from ..events import (
    AgentConfirmationDenied,
    AgentConfirmationGranted,
    AgentPlanCompleted,
    AgentReplanFailed,
    AgentReplanned,
    AgentReplanRequested,
    AgentStepEvaluated,
    EventBus,
    ToolConfirmationRequired,
    ToolExecuted,
    ToolFailed,
    ToolRequested,
)
from ..logging import get_logger
from .agent_models import AgentPlan, AgentTask, TaskStatus
from .observation import Observation

if TYPE_CHECKING:
    from ..memory.plan_store import AgentPlanStore
    from ..tools.registry import ToolRegistry
    from .replanner import AgentReplanner


@dataclass
class AgentExecutionResult:
    """Encapsulates the execution summary of an AgentPlan run by AgentExecutor."""

    plan_id: str
    steps_executed: int = 0
    completed: bool = False
    failed: bool = False
    waiting_confirmation: bool = False
    executed_tasks: list[AgentTask] = field(default_factory=list)


class AgentExecutor:
    """Executes multi-step AgentPlans deterministically without making direct LLM calls."""

    DEFAULT_MAX_AGENT_STEPS: int = 5

    def __init__(
        self,
        max_agent_steps: int = DEFAULT_MAX_AGENT_STEPS,
        event_bus: EventBus | None = None,
        registry: ToolRegistry | None = None,
        evaluator: TaskEvaluator | None = None,
        replanner: AgentReplanner | None = None,
        plan_store: AgentPlanStore | None = None,
        verifier: ActionVerifier | None = None,
        reflector: CognitiveReflector | None = None,
    ) -> None:
        self.max_agent_steps = max_agent_steps
        self.event_bus = event_bus
        self.registry = registry
        self.evaluator = evaluator or TaskEvaluator()
        self.replanner = replanner
        self.plan_store = plan_store
        self.verifier = verifier or ActionVerifier()
        self.reflector = reflector or CognitiveReflector()

    def authorize_task(self, plan: AgentPlan, task_id: str) -> bool:
        """Authorizes a single task in WAITING_CONFIRMATION state to allow execution."""
        task = next((t for t in plan.tasks if t.task_id == task_id), None)
        if task is None or task.status != TaskStatus.WAITING_CONFIRMATION:
            return False

        task.status = TaskStatus.PENDING
        task.parameters["_authorized"] = True

        if self.event_bus is not None:
            self.event_bus.publish(
                AgentConfirmationGranted(
                    source="AgentExecutor",
                    plan_id=plan.plan_id,
                    task_id=task.task_id,
                    tool_name=task.tool_name or "",
                )
            )

        return True

    def deny_task(
        self, plan: AgentPlan, task_id: str, reason: str = "User denied execution"
    ) -> bool:
        """Denies a single task in WAITING_CONFIRMATION state, setting its status to FAILED."""
        task = next((t for t in plan.tasks if t.task_id == task_id), None)
        if task is None or task.status != TaskStatus.WAITING_CONFIRMATION:
            return False

        task.status = TaskStatus.FAILED
        task.error = f"Confirmation denied: {reason}"

        if self.event_bus is not None:
            self.event_bus.publish(
                AgentConfirmationDenied(
                    source="AgentExecutor",
                    plan_id=plan.plan_id,
                    task_id=task.task_id,
                    tool_name=task.tool_name or "",
                    reason=reason,
                )
            )

        return True

    def resume_plan(
        self, plan: AgentPlan, registry: ToolRegistry | None = None
    ) -> AgentExecutionResult:
        """Resumes execution of an AgentPlan starting from the next pending task."""
        return self.execute_plan(plan, registry=registry)

    def execute_plan(
        self,
        plan: AgentPlan,
        registry: ToolRegistry | None = None,
    ) -> AgentExecutionResult:
        """Executes pending tasks in plan up to max_agent_steps safely."""
        logger = get_logger("AgentExecutor")
        active_registry = registry or self.registry

        result = AgentExecutionResult(plan_id=plan.plan_id)

        if not plan.tasks:
            logger.info(f"AgentPlan '{plan.plan_id}' is empty. Execution completed immediately.")
            result.completed = True
            return result

        steps_count = 0

        last_verification = None
        last_reflection = None

        while steps_count < self.max_agent_steps:
            # If plan is already completed, failed, or waiting confirmation, stop loop
            if plan.is_failed():
                result.failed = True
                break

            if plan.is_waiting_confirmation():
                result.waiting_confirmation = True
                break

            task = plan.get_next_pending_task()
            if task is None:
                # No more pending tasks
                break

            # Execute task
            steps_count += 1
            task.status = TaskStatus.IN_PROGRESS
            result.executed_tasks.append(task)

            # If task specifies a tool, execute via registry
            if task.tool_name:
                if active_registry is None:
                    task.status = TaskStatus.FAILED
                    task.error = f"ToolRegistry not available to execute tool '{task.tool_name}'"
                    result.failed = True
                    break

                tool = active_registry.get(task.tool_name)
                if tool is None:
                    task.status = TaskStatus.FAILED
                    task.error = f"Tool '{task.tool_name}' not registered in ToolRegistry"
                    result.failed = True
                    break

                # Safety Check: confirmation or destructive risk level
                is_dangerous = (
                    tool.metadata.requires_confirmation or tool.metadata.risk_level == "destructive"
                )
                is_authorized = bool(task.parameters.get("_authorized", False))

                if is_dangerous and not is_authorized:
                    task.status = TaskStatus.WAITING_CONFIRMATION
                    task.error = f"Tool '{task.tool_name}' requires confirmation"
                    result.waiting_confirmation = True
                    if self.event_bus is not None:
                        self.event_bus.publish(
                            ToolConfirmationRequired(
                                source="AgentExecutor",
                                tool_name=task.tool_name,
                                risk_level=tool.metadata.risk_level,
                                reason=f"Task '{task.description}' requires user confirmation",
                            )
                        )
                    break

                # Publish start event
                if self.event_bus is not None:
                    self.event_bus.publish(
                        ToolRequested(
                            source="AgentExecutor",
                            tool_name=task.tool_name,
                            raw_text=task.description,
                        )
                    )

                # Clean temporary authorization flag & clear previous pause error before execution
                task.parameters.pop("_authorized", None)
                task.error = None

                # Execute tool deterministically
                tool_result = active_registry.execute(task.tool_name, **task.parameters)

                # Action Verification & Cognitive Reflection
                expected_outcome = task.parameters.get("expected_outcome") or task.parameters.get(
                    "expected"
                )
                ver_res = self.verifier.verify(
                    task, tool_result=tool_result, expected_outcome=expected_outcome
                )
                ref_summary = self.reflector.reflect(ver_res)
                last_verification = ver_res
                last_reflection = ref_summary

                obs = Observation.from_tool_result(task.task_id, tool_result)
                obs.metadata["verification"] = ver_res
                obs.metadata["reflection"] = ref_summary

                # Publish tool execution event
                if self.event_bus is not None:
                    if tool_result.success:
                        self.event_bus.publish(
                            ToolExecuted(
                                source="AgentExecutor",
                                tool_name=task.tool_name,
                                success=True,
                                execution_time_ms=getattr(tool_result, "execution_time_ms", 0.0),
                            )
                        )
                    else:
                        self.event_bus.publish(
                            ToolFailed(
                                source="AgentExecutor",
                                tool_name=task.tool_name,
                                error=tool_result.error or "Unknown tool execution error",
                            )
                        )

                # Evaluate step outcome
                eval_res = self.evaluator.evaluate(task, obs)

                # Publish evaluation event
                if self.event_bus is not None:
                    self.event_bus.publish(
                        AgentStepEvaluated(
                            source="AgentExecutor",
                            plan_id=plan.plan_id,
                            task_id=task.task_id,
                            evaluation_status=eval_res.status.value,
                            reason=eval_res.reason,
                        )
                    )

                # Process evaluation status (incorporating VerificationResult & ReflectionSummary)
                if eval_res.status == EvaluationStatus.SUCCESS:
                    task.status = TaskStatus.SUCCESS
                    task.result = tool_result.output
                    # Reset retry counter on success
                    task.parameters.pop("_retry_count", None)
                elif (
                    ver_res.status == VerificationStatus.TRANSIENT_FAILURE
                    and ref_summary.recommended_action == "RETRY"
                    and int(task.parameters.get("_max_retries", 0)) > 0
                ):
                    # Check retry limit
                    _retry_count = int(task.parameters.get("_retry_count", 0))
                    _max_retries = int(task.parameters.get("_max_retries", 0))
                    if _retry_count < _max_retries:
                        task.parameters["_retry_count"] = _retry_count + 1
                        task.status = TaskStatus.PENDING
                        steps_count -= 1
                    else:
                        task.status = TaskStatus.FAILED
                        task.error = f"Exhausted retries ({_max_retries}): {ref_summary.root_cause}"
                        result.failed = True
                        if self.replanner is not None:
                            if self.event_bus is not None:
                                self.event_bus.publish(
                                    AgentReplanRequested(
                                        source="AgentExecutor",
                                        plan_id=plan.plan_id,
                                        task_id=task.task_id,
                                        replan_count=plan.replan_count,
                                        reason=task.error,
                                    )
                                )
                            replan_ok = self.replanner.replan(
                                plan=plan,
                                failed_task=task,
                                observation=obs,
                                eval_result=eval_res,
                                registry=active_registry,
                                reflection=ref_summary,
                                verification=ver_res,
                            )
                            if replan_ok:
                                if self.event_bus is not None:
                                    self.event_bus.publish(
                                        AgentReplanned(
                                            source="AgentExecutor",
                                            plan_id=plan.plan_id,
                                            task_id=task.task_id,
                                            replan_count=plan.replan_count,
                                            new_tasks_count=len(plan.tasks),
                                        )
                                    )
                                result.failed = False
                                if self.plan_store is not None:
                                    self.plan_store.update_plan(plan)
                                continue
                            else:
                                if self.event_bus is not None:
                                    self.event_bus.publish(
                                        AgentReplanFailed(
                                            source="AgentExecutor",
                                            plan_id=plan.plan_id,
                                            task_id=task.task_id,
                                            replan_count=plan.replan_count,
                                            reason=f"Replanning failed: {task.error}",
                                        )
                                    )
                                task.error = (
                                    "Task execution failed and replanning was unsuccessful: "
                                    f"{task.error}"
                                )
                        break
                elif eval_res.status == EvaluationStatus.REPLAN_REQUIRED:
                    task.status = TaskStatus.FAILED
                    task.error = eval_res.reason
                    result.failed = True
                    if self.replanner is not None:
                        if self.event_bus is not None:
                            self.event_bus.publish(
                                AgentReplanRequested(
                                    source="AgentExecutor",
                                    plan_id=plan.plan_id,
                                    task_id=task.task_id,
                                    replan_count=plan.replan_count,
                                    reason=eval_res.reason,
                                )
                            )
                        replan_ok = self.replanner.replan(
                            plan=plan,
                            failed_task=task,
                            observation=obs,
                            eval_result=eval_res,
                            registry=active_registry,
                            reflection=ref_summary,
                            verification=ver_res,
                        )
                        if replan_ok:
                            if self.event_bus is not None:
                                self.event_bus.publish(
                                    AgentReplanned(
                                        source="AgentExecutor",
                                        plan_id=plan.plan_id,
                                        task_id=task.task_id,
                                        replan_count=plan.replan_count,
                                        new_tasks_count=len(plan.tasks),
                                    )
                                )
                            result.failed = False
                            if self.plan_store is not None:
                                self.plan_store.update_plan(plan)
                            continue
                        else:
                            if self.event_bus is not None:
                                self.event_bus.publish(
                                    AgentReplanFailed(
                                        source="AgentExecutor",
                                        plan_id=plan.plan_id,
                                        task_id=task.task_id,
                                        replan_count=plan.replan_count,
                                        reason=f"Replanning failed: {eval_res.reason}",
                                    )
                                )
                            task.error = (
                                "Task execution failed and replanning was unsuccessful: "
                                f"{eval_res.reason}"
                            )
                    break
                else:
                    task.status = TaskStatus.FAILED
                    task.error = eval_res.reason
                    result.failed = True
                    if self.event_bus is not None:
                        self.event_bus.publish(
                            ToolFailed(
                                source="AgentExecutor",
                                tool_name=task.tool_name,
                                error=task.error,
                            )
                        )
                    break

            else:
                # Task without tool execution
                ver_res = self.verifier.verify(task, expected_outcome="Completed")
                ref_summary = self.reflector.reflect(ver_res)
                last_verification = ver_res
                last_reflection = ref_summary
                obs = Observation(task_id=task.task_id, success=True, output="Completed")
                obs.metadata["verification"] = ver_res
                obs.metadata["reflection"] = ref_summary
                eval_res = self.evaluator.evaluate(task, obs)
                if eval_res.status == EvaluationStatus.SUCCESS:
                    task.status = TaskStatus.SUCCESS
                    task.result = "Completed"
                else:
                    task.status = TaskStatus.FAILED
                    task.error = eval_res.reason
                    result.failed = True
                    break

        result.steps_executed = steps_count
        result.completed = plan.is_completed()
        result.failed = plan.is_failed()
        result.waiting_confirmation = plan.is_waiting_confirmation()

        if self.plan_store is not None:
            self.plan_store.update_plan(plan)

        if self.event_bus is not None:
            self.event_bus.publish(
                AgentPlanCompleted(
                    source="AgentExecutor",
                    plan_id=plan.plan_id,
                    completed=result.completed,
                    failed=result.failed,
                    waiting_confirmation=result.waiting_confirmation,
                    steps_executed=result.steps_executed,
                    duration_ms=0.0,
                    verification=last_verification,
                    reflection=last_reflection,
                )
            )

        return result
