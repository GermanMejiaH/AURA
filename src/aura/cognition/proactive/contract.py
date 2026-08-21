"""Stage 23 — Proactive Assistant Task Contracts & Trigger Definitions.

Defines strongly typed data structures for event-driven proactive tasks,
trigger condition specifications, action proposals, and grounded notifications.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class TriggerType(str, Enum):
    """Supported proactive trigger condition types."""

    TIME_CONDITION = "TIME_CONDITION"
    SYSTEM_CONDITION = "SYSTEM_CONDITION"
    PROCESS_CONDITION = "PROCESS_CONDITION"
    EVENT_CONDITION = "EVENT_CONDITION"


class ProactiveTaskStatus(str, Enum):
    """Closed-loop lifecycle states of a proactive task."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


@dataclass
class TriggerDefinition:
    """Strongly typed trigger specification for proactive evaluation."""

    trigger_type: TriggerType
    target_time_iso: str | None = None
    interval_seconds: float | None = None
    metric_name: str | None = None  # e.g., "cpu", "memory", "disk"
    operator: str | None = None  # "<", ">", "<=", ">=", "=="
    threshold_value: float | None = None
    process_name: str | None = None
    event_name: str | None = None
    extra_params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["trigger_type"] = self.trigger_type.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriggerDefinition:
        t_type = TriggerType(data.get("trigger_type", TriggerType.TIME_CONDITION.value))
        return cls(
            trigger_type=t_type,
            target_time_iso=data.get("target_time_iso"),
            interval_seconds=data.get("interval_seconds"),
            metric_name=data.get("metric_name"),
            operator=data.get("operator"),
            threshold_value=data.get("threshold_value"),
            process_name=data.get("process_name"),
            event_name=data.get("event_name"),
            extra_params=data.get("extra_params", {}),
        )


@dataclass
class ActionProposal:
    """Action tool proposal to be evaluated exclusively by Stage 16 RuntimeOrchestrator."""

    tool_name: str
    tool_kwargs: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionProposal:
        return cls(
            tool_name=data.get("tool_name", ""),
            tool_kwargs=data.get("tool_kwargs", {}),
            description=data.get("description", ""),
        )


@dataclass
class ProactiveTask:
    """Persistent, event-driven proactive task contract."""

    task_id: str = field(default_factory=lambda: f"ptask_{uuid.uuid4().hex[:12]}")
    conversation_id: str = "default_conv"
    creation_turn_id: str = "turn_0"
    trigger_type: TriggerType = TriggerType.TIME_CONDITION
    trigger_definition: TriggerDefinition = field(
        default_factory=lambda: TriggerDefinition(trigger_type=TriggerType.TIME_CONDITION)
    )
    action_proposal: ActionProposal = field(
        default_factory=lambda: ActionProposal(tool_name="system_status_tool")
    )
    status: ProactiveTaskStatus = ProactiveTaskStatus.PENDING
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)
    next_evaluation_at: str | None = None
    last_evaluation_at: str | None = None
    execution_count: int = 0
    max_executions: int = 1
    expires_at: str | None = None
    correlation_id: str = field(default_factory=lambda: f"corr_{uuid.uuid4().hex[:12]}")
    operation_id: str | None = None
    last_execution_id: str | None = None
    last_outcome_id: str | None = None
    cancellation_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "conversation_id": self.conversation_id,
            "creation_turn_id": self.creation_turn_id,
            "trigger_type": self.trigger_type.value,
            "trigger_definition": self.trigger_definition.to_dict(),
            "action_proposal": self.action_proposal.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "next_evaluation_at": self.next_evaluation_at,
            "last_evaluation_at": self.last_evaluation_at,
            "execution_count": self.execution_count,
            "max_executions": self.max_executions,
            "expires_at": self.expires_at,
            "correlation_id": self.correlation_id,
            "operation_id": self.operation_id,
            "last_execution_id": self.last_execution_id,
            "last_outcome_id": self.last_outcome_id,
            "cancellation_reason": self.cancellation_reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProactiveTask:
        t_def_raw = data.get("trigger_definition", {})
        t_def = (
            TriggerDefinition.from_dict(t_def_raw)
            if isinstance(t_def_raw, dict)
            else TriggerDefinition(trigger_type=TriggerType.TIME_CONDITION)
        )

        a_prop_raw = data.get("action_proposal", {})
        a_prop = (
            ActionProposal.from_dict(a_prop_raw)
            if isinstance(a_prop_raw, dict)
            else ActionProposal(tool_name="system_status_tool")
        )

        return cls(
            task_id=data.get("task_id", f"ptask_{uuid.uuid4().hex[:12]}"),
            conversation_id=data.get("conversation_id", "default_conv"),
            creation_turn_id=data.get("creation_turn_id", "turn_0"),
            trigger_type=TriggerType(data.get("trigger_type", TriggerType.TIME_CONDITION.value)),
            trigger_definition=t_def,
            action_proposal=a_prop,
            status=ProactiveTaskStatus(data.get("status", ProactiveTaskStatus.PENDING.value)),
            created_at=data.get("created_at", _utcnow_iso()),
            updated_at=data.get("updated_at", _utcnow_iso()),
            next_evaluation_at=data.get("next_evaluation_at"),
            last_evaluation_at=data.get("last_evaluation_at"),
            execution_count=int(data.get("execution_count", 0)),
            max_executions=int(data.get("max_executions", 1)),
            expires_at=data.get("expires_at"),
            correlation_id=data.get("correlation_id", f"corr_{uuid.uuid4().hex[:12]}"),
            operation_id=data.get("operation_id"),
            last_execution_id=data.get("last_execution_id"),
            last_outcome_id=data.get("last_outcome_id"),
            cancellation_reason=data.get("cancellation_reason"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ProactiveNotification:
    """Grounded result notification produced following Stage 16 operation execution."""

    notification_id: str = field(default_factory=lambda: f"pnotif_{uuid.uuid4().hex[:12]}")
    task_id: str = ""
    conversation_id: str = ""
    title: str = ""
    content: str = ""
    success: bool = True
    created_at: str = field(default_factory=_utcnow_iso)
    delivered: bool = False
    operation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
