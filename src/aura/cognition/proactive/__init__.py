"""Stage 23 — Proactive Assistant Runtime Package."""

from .contract import (
    ActionProposal,
    ProactiveNotification,
    ProactiveTask,
    ProactiveTaskStatus,
    TriggerDefinition,
    TriggerType,
)
from .detectors import (
    EventBusTriggerDetector,
    ProcessConditionDetector,
    SystemConditionDetector,
    TimeTriggerDetector,
)
from .evaluator import ProactiveTaskEvaluator
from .store import ProactiveTaskStore

__all__ = [
    "ActionProposal",
    "EventBusTriggerDetector",
    "ProactiveNotification",
    "ProactiveTask",
    "ProactiveTaskEvaluator",
    "ProactiveTaskStatus",
    "ProactiveTaskStore",
    "ProcessConditionDetector",
    "SystemConditionDetector",
    "TimeTriggerDetector",
    "TriggerDefinition",
    "TriggerType",
]
