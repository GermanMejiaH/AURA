"""Stage 23 — Proactive Condition Detectors.

Provides condition evaluation detectors for time, host system metrics,
process status, and EventBus domain events. Detectors are strictly read-only
evaluators with ZERO executive authority.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from aura.events import Event, EventBus
from aura.logging import get_logger
from aura.tools.system_observation import RealSystemObservationTool

from .contract import ProactiveTask, TriggerType

logger = get_logger("ConditionDetectors")


class BaseConditionDetector(ABC):
    """Abstract base class for proactive condition detectors."""

    @abstractmethod
    def evaluate_trigger(self, task: ProactiveTask, **kwargs: Any) -> bool:
        """Evaluates whether the proactive task trigger condition is satisfied.

        Returns True if condition is met, False otherwise. ZERO tool execution allowed.
        """
        pass


class TimeTriggerDetector(BaseConditionDetector):
    """Evaluates time-based trigger conditions (scheduled time or elapsed intervals)."""

    def evaluate_trigger(self, task: ProactiveTask, **kwargs: Any) -> bool:
        if task.trigger_type != TriggerType.TIME_CONDITION:
            return False

        t_def = task.trigger_definition
        now = datetime.now(UTC)

        # 1. Fixed Target Time Evaluation
        if t_def.target_time_iso:
            try:
                target_dt = datetime.fromisoformat(t_def.target_time_iso)
                if target_dt.tzinfo is None:
                    target_dt = target_dt.replace(tzinfo=UTC)
            except ValueError as val_err:
                logger.warning(f"Invalid target_time_iso '{t_def.target_time_iso}': {val_err}")
                return False
            else:
                return now >= target_dt

        # 2. Elapsed Interval Evaluation
        if t_def.interval_seconds is not None and t_def.interval_seconds > 0:
            ref_iso = task.last_evaluation_at or task.created_at
            try:
                ref_dt = datetime.fromisoformat(ref_iso)
                if ref_dt.tzinfo is None:
                    ref_dt = ref_dt.replace(tzinfo=UTC)
                elapsed_sec = (now - ref_dt).total_seconds()
            except ValueError:
                return False
            else:
                return elapsed_sec >= t_def.interval_seconds

        return False


class SystemConditionDetector(BaseConditionDetector):
    """Evaluates host system metric conditions (CPU, Memory, Disk free space)."""

    def __init__(self, sys_tool: RealSystemObservationTool | None = None) -> None:
        self.sys_tool = sys_tool or RealSystemObservationTool()

    def evaluate_trigger(self, task: ProactiveTask, **kwargs: Any) -> bool:
        if task.trigger_type != TriggerType.SYSTEM_CONDITION:
            return False

        t_def = task.trigger_definition
        metric_name = (t_def.metric_name or "").lower().strip()
        operator = t_def.operator or ">"
        threshold = t_def.threshold_value

        if threshold is None:
            return False

        # Execute read-only host observation metric query
        obs_res = self.sys_tool.execute(action=metric_name or "all")
        if not obs_res.success or not isinstance(obs_res.output, dict):
            return False

        output = obs_res.output
        actual_value: float | None = None

        if metric_name in ("cpu", "cpu_percent"):
            actual_value = float(output.get("cpu_percent", 0.0))
        elif metric_name in ("memory", "memory_available_mb"):
            actual_value = float(output.get("memory_available_mb", 0.0))
        elif metric_name in ("disk", "disk_free_gb"):
            actual_value = float(output.get("disk_free_gb", 0.0))
        else:
            # Check direct key match in output dictionary
            if metric_name in output and isinstance(output[metric_name], (int, float)):
                actual_value = float(output[metric_name])

        if actual_value is None:
            return False

        return self._compare(actual_value, operator, threshold)

    @staticmethod
    def _compare(actual: float, op: str, threshold: float) -> bool:
        if op == ">":
            return actual > threshold
        if op == ">=":
            return actual >= threshold
        if op == "<":
            return actual < threshold
        if op == "<=":
            return actual <= threshold
        if op in ("==", "="):
            return abs(actual - threshold) < 1e-6
        return False


class ProcessConditionDetector(BaseConditionDetector):
    """Evaluates process status conditions (process running or process terminated)."""

    def __init__(self, sys_tool: RealSystemObservationTool | None = None) -> None:
        self.sys_tool = sys_tool or RealSystemObservationTool()

    def evaluate_trigger(self, task: ProactiveTask, **kwargs: Any) -> bool:
        if task.trigger_type != TriggerType.PROCESS_CONDITION:
            return False

        t_def = task.trigger_definition
        target_process = (t_def.process_name or "").lower().strip()
        expected_state = (t_def.extra_params.get("expected_state") or "terminated").lower()

        if not target_process:
            return False

        obs_res = self.sys_tool.execute(action="processes")
        if not obs_res.success or not isinstance(obs_res.output, dict):
            return False

        processes: list[dict[str, Any]] = obs_res.output.get("top_processes", [])
        is_running = any(target_process in str(p.get("name", "")).lower() for p in processes)

        if expected_state == "running":
            return is_running
        if expected_state == "terminated":
            return not is_running

        return False


class EventBusTriggerDetector(BaseConditionDetector):
    """Evaluates domain event occurrence triggers registered on EventBus."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self._triggered_events: set[str] = set()

        if self.event_bus:
            self.event_bus.subscribe("*", self._on_event)

    def _on_event(self, event: Event) -> None:
        event_name = event.event_name()
        self._triggered_events.add(event_name)

    def evaluate_trigger(self, task: ProactiveTask, **kwargs: Any) -> bool:
        if task.trigger_type != TriggerType.EVENT_CONDITION:
            return False

        t_def = task.trigger_definition
        expected_event = t_def.event_name or ""

        # Check explicit passed event_name or event history buffer
        received_event = kwargs.get("event_name")
        if received_event and received_event == expected_event:
            return True

        if expected_event in self._triggered_events:
            # Clear consumed event from set
            self._triggered_events.remove(expected_event)
            return True

        return False
