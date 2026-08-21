"""Stage 23 — Proactive Task Evaluator & Event-Driven Engine.

Coordinates trigger evaluation, atomic task claiming, proposal generation,
and execution submission strictly through Stage 16 RuntimeOrchestrator.
ZERO direct tool execution capability.
"""

from __future__ import annotations

import threading
from typing import Any

from aura.events import EventBus
from aura.logging import get_logger
from aura.tools.registry import ToolRegistry

from ..scheduling.orchestration import RuntimeOperation, RuntimeOperationState, RuntimeOrchestrator
from .contract import (
    ProactiveNotification,
    ProactiveTask,
    ProactiveTaskStatus,
    TriggerType,
)
from .detectors import (
    EventBusTriggerDetector,
    ProcessConditionDetector,
    SystemConditionDetector,
    TimeTriggerDetector,
)
from .store import ProactiveTaskStore

logger = get_logger("ProactiveTaskEvaluator")


class ProactiveTaskEvaluator:
    """Evaluates proactive task triggers and dispatches action proposals via Stage 16."""

    def __init__(
        self,
        orchestrator: RuntimeOrchestrator,
        tool_registry: ToolRegistry,
        store: ProactiveTaskStore | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.tool_registry = tool_registry
        self.store = store or ProactiveTaskStore()
        self.event_bus = event_bus
        self._lock = threading.RLock()

        # Initialize condition detectors (strictly read-only)
        self.time_detector = TimeTriggerDetector()
        self.system_detector = SystemConditionDetector()
        self.process_detector = ProcessConditionDetector()
        self.event_detector = EventBusTriggerDetector(event_bus=event_bus)

    def evaluate_active_tasks(self, **kwargs: Any) -> list[ProactiveNotification]:
        """Evaluates active tasks. Claims matching tasks and submits proposals to Stage 16."""
        notifications: list[ProactiveNotification] = []
        active_tasks = self.store.list_active_tasks()

        for task in active_tasks:
            try:
                notif = self.evaluate_single_task(task, **kwargs)
                if notif is not None:
                    notifications.append(notif)
            except Exception as exc:
                logger.error(f"Error evaluating proactive task '{task.task_id}': {exc}")

        return notifications

    def evaluate_single_task(
        self, task: ProactiveTask, **kwargs: Any
    ) -> ProactiveNotification | None:
        """Evaluates a single proactive task for trigger match and dispatches through Stage 16."""
        with self._lock:
            # 1. Evaluate Trigger Match via appropriate condition detector
            matched = self._check_trigger_match(task, **kwargs)
            if not matched:
                return None

            logger.info(
                f"Proactive trigger matched for task '{task.task_id}' "
                f"[{task.trigger_type.value}]. Attempting atomic claim..."
            )

            # 2. Atomic Claim in SQLite (Guarantees idempotency)
            claimed = self.store.claim_task_for_execution(task.task_id)
            if not claimed:
                logger.warning(
                    f"Task '{task.task_id}' claim rejected (already claimed or inactive)."
                )
                return None

            # 3. Formulate Tool Action Call Proposal (No direct execution!)
            proposal = task.action_proposal
            tool_name = proposal.tool_name
            tool_kwargs = proposal.tool_kwargs or {}

            # Validate tool in ToolRegistry
            if not self.tool_registry.get(tool_name):
                err_msg = f"Unknown tool '{tool_name}' in proactive action proposal."
                logger.error(err_msg)
                self.store.update_task_status(
                    task.task_id,
                    ProactiveTaskStatus.FAILED,
                    cancellation_reason=err_msg,
                )
                notif = ProactiveNotification(
                    task_id=task.task_id,
                    conversation_id=task.conversation_id,
                    title=f"Tarea Fallida: {proposal.description or tool_name}",
                    content=f"Error en propuesta: {err_msg}",
                    success=False,
                )
                self.store.save_notification(notif)
                return notif

            # 4. Dispatch Action Proposal strictly to Stage 16 RuntimeOrchestrator
            # Action closure invokes tool_registry.execute(...) only when Stage 16 reaches Stage 12
            def _orchestrated_action_closure() -> Any:
                res = self.tool_registry.execute(tool_name, **tool_kwargs)
                if not res.success:
                    raise RuntimeError(res.error or f"Tool '{tool_name}' execution failed")
                return res.output

            op: RuntimeOperation = self.orchestrator.execute_closed_loop(
                action_id=tool_name,
                goal_id=task.task_id,
                correlation_id=task.correlation_id,
                action_fn=_orchestrated_action_closure,
                metadata={
                    "proactive_task_id": task.task_id,
                    "conversation_id": task.conversation_id,
                    "description": proposal.description,
                },
            )

            # 5. Process Stage 16 Operation Result & Persist Task State
            return self._handle_operation_result(task, op, proposal.description or tool_name)

    def _check_trigger_match(self, task: ProactiveTask, **kwargs: Any) -> bool:
        if task.trigger_type == TriggerType.TIME_CONDITION:
            return self.time_detector.evaluate_trigger(task, **kwargs)
        if task.trigger_type == TriggerType.SYSTEM_CONDITION:
            return self.system_detector.evaluate_trigger(task, **kwargs)
        if task.trigger_type == TriggerType.PROCESS_CONDITION:
            return self.process_detector.evaluate_trigger(task, **kwargs)
        if task.trigger_type == TriggerType.EVENT_CONDITION:
            return self.event_detector.evaluate_trigger(task, **kwargs)
        return False

    def _handle_operation_result(
        self,
        task: ProactiveTask,
        op: RuntimeOperation,
        action_desc: str,
    ) -> ProactiveNotification:
        new_count = task.execution_count + 1
        is_completed = new_count >= task.max_executions

        if op.state == RuntimeOperationState.COMPLETED:
            final_status = (
                ProactiveTaskStatus.COMPLETED if is_completed else ProactiveTaskStatus.ACTIVE
            )
            self.store.update_task_status(
                task.task_id,
                status=final_status,
                operation_id=op.operation_id,
                increment_execution_count=True,
            )

            content_text = f"Acción '{action_desc}' ejecutada con éxito mediante Stage 16."
            notif = ProactiveNotification(
                task_id=task.task_id,
                conversation_id=task.conversation_id,
                title=f"Recordatorio Proactivo: {action_desc}",
                content=content_text,
                success=True,
                operation_id=op.operation_id,
            )

        elif op.state == RuntimeOperationState.BLOCKED:
            reason_text = op.failure_reason or "Bloqueado por Policy/Governance/SafeMode"
            self.store.update_task_status(
                task.task_id,
                status=ProactiveTaskStatus.BLOCKED,
                operation_id=op.operation_id,
                cancellation_reason=reason_text,
            )

            content_text = f"Acción '{action_desc}' fue BLOQUEADA por runtime ({reason_text})."
            notif = ProactiveNotification(
                task_id=task.task_id,
                conversation_id=task.conversation_id,
                title=f"Acción Bloqueada: {action_desc}",
                content=content_text,
                success=False,
                operation_id=op.operation_id,
            )

        else:
            err_text = op.failure_reason or f"Fallo en operacion state={op.state.value}"
            self.store.update_task_status(
                task.task_id,
                status=ProactiveTaskStatus.FAILED,
                operation_id=op.operation_id,
                cancellation_reason=err_text,
            )

            content_text = f"Acción '{action_desc}' falló en ejecución gobernada ({err_text})."
            notif = ProactiveNotification(
                task_id=task.task_id,
                conversation_id=task.conversation_id,
                title=f"Fallo Proactivo: {action_desc}",
                content=content_text,
                success=False,
                operation_id=op.operation_id,
            )

        self.store.save_notification(notif)
        return notif
