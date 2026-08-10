from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Event:
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=_utcnow)
    source: str = "system"
    payload: dict[str, Any] = field(default_factory=dict)

    __event_name__: ClassVar[str] = ""

    @classmethod
    def event_name(cls) -> str:
        if cls.__event_name__:
            return cls.__event_name__
        return cls.__name__

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_type"] = self.event_name()
        return data

    def __repr__(self) -> str:
        return f"<{self.event_name()} id={self.event_id} ts={self.timestamp.isoformat()}>"


@dataclass(frozen=True)
class SystemBooting(Event):
    __event_name__: ClassVar[str] = "SystemBooting"


@dataclass(frozen=True)
class SystemInitialized(Event):
    __event_name__: ClassVar[str] = "SystemInitialized"


@dataclass(frozen=True)
class SystemReady(Event):
    __event_name__: ClassVar[str] = "SystemReady"


@dataclass(frozen=True)
class SystemShutdownRequested(Event):
    reason: str = "manual"
    __event_name__: ClassVar[str] = "SystemShutdownRequested"


@dataclass(frozen=True)
class SystemShuttingDown(Event):
    __event_name__: ClassVar[str] = "SystemShuttingDown"


@dataclass(frozen=True)
class SystemStopped(Event):
    exit_code: int = 0
    __event_name__: ClassVar[str] = "SystemStopped"


@dataclass(frozen=True)
class ModuleLoaded(Event):
    module_name: str = ""
    __event_name__: ClassVar[str] = "ModuleLoaded"


@dataclass(frozen=True)
class ModuleStarted(Event):
    module_name: str = ""
    __event_name__: ClassVar[str] = "ModuleStarted"


@dataclass(frozen=True)
class ModuleStopped(Event):
    module_name: str = ""
    __event_name__: ClassVar[str] = "ModuleStopped"


@dataclass(frozen=True)
class ErrorOccurred(Event):
    error_type: str = ""
    error_message: str = ""
    module: str = ""
    recoverable: bool = True
    __event_name__: ClassVar[str] = "ErrorOccurred"


@dataclass(frozen=True)
class LogEntryCreated(Event):
    level: str = "INFO"
    message: str = ""
    logger_name: str = ""
    __event_name__: ClassVar[str] = "LogEntryCreated"


@dataclass(frozen=True)
class ConfigLoaded(Event):
    config_keys: int = 0
    source: str = "default"
    __event_name__: ClassVar[str] = "ConfigLoaded"


@dataclass(frozen=True)
class HealthCheckPerformed(Event):
    overall_status: str = "healthy"
    modules_checked: int = 0
    modules_healthy: int = 0
    __event_name__: ClassVar[str] = "HealthCheckPerformed"


@dataclass(frozen=True)
class LifecycleStateChanged(Event):
    previous_state: str = ""
    new_state: str = ""
    __event_name__: ClassVar[str] = "LifecycleStateChanged"


@dataclass(frozen=True)
class EntityCreated(Event):
    entity_id: str = ""
    entity_type: str = ""
    entity_name: str = ""
    __event_name__: ClassVar[str] = "EntityCreated"


@dataclass(frozen=True)
class EntityUpdated(Event):
    entity_id: str = ""
    entity_type: str = ""
    updated_fields: tuple[str, ...] = ()
    __event_name__: ClassVar[str] = "EntityUpdated"


@dataclass(frozen=True)
class EntityDeleted(Event):
    entity_id: str = ""
    __event_name__: ClassVar[str] = "EntityDeleted"


@dataclass(frozen=True)
class RelationCreated(Event):
    relation_id: str = ""
    source_id: str = ""
    target_id: str = ""
    relation_type: str = ""
    __event_name__: ClassVar[str] = "RelationCreated"


@dataclass(frozen=True)
class RelationDeleted(Event):
    relation_id: str = ""
    __event_name__: ClassVar[str] = "RelationDeleted"


@dataclass(frozen=True)
class WorldModelUpdated(Event):
    entities_count: int = 0
    relations_count: int = 0
    change_type: str = "update"
    __event_name__: ClassVar[str] = "WorldModelUpdated"


@dataclass(frozen=True)
class CognitiveStateChanged(Event):
    previous_state: str = ""
    new_state: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "CognitiveStateChanged"


@dataclass(frozen=True)
class AttentionFocused(Event):
    target: str = ""
    priority: int = 0
    reason: str = ""
    __event_name__: ClassVar[str] = "AttentionFocused"


@dataclass(frozen=True)
class GoalSet(Event):
    goal_id: str = ""
    description: str = ""
    priority: int = 1
    __event_name__: ClassVar[str] = "GoalSet"


@dataclass(frozen=True)
class GoalAchieved(Event):
    goal_id: str = ""
    __event_name__: ClassVar[str] = "GoalAchieved"


@dataclass(frozen=True)
class PlanCreated(Event):
    plan_id: str = ""
    goal_id: str = ""
    steps_count: int = 0
    __event_name__: ClassVar[str] = "PlanCreated"


@dataclass(frozen=True)
class StepExecuted(Event):
    plan_id: str = ""
    step_id: str = ""
    success: bool = True
    result: str = ""
    __event_name__: ClassVar[str] = "StepExecuted"


@dataclass(frozen=True)
class ActionDispatched(Event):
    action_id: str = ""
    action_type: str = ""
    target: str = ""
    __event_name__: ClassVar[str] = "ActionDispatched"


@dataclass(frozen=True)
class WakeWordDetected(Event):
    keyword: str = "aura"
    confidence: float = 1.0
    __event_name__: ClassVar[str] = "WakeWordDetected"


@dataclass(frozen=True)
class SpeechRecognized(Event):
    text: str = ""
    confidence: float = 1.0
    language: str = "es"
    __event_name__: ClassVar[str] = "SpeechRecognized"


@dataclass(frozen=True)
class SpeechSynthesized(Event):
    text: str = ""
    audio_bytes_length: int = 0
    __event_name__: ClassVar[str] = "SpeechSynthesized"


@dataclass(frozen=True)
class SilenceDetected(Event):
    duration_seconds: float = 0.0
    __event_name__: ClassVar[str] = "SilenceDetected"


@dataclass(frozen=True)
class AudioPlaybackStarted(Event):
    text: str = ""
    __event_name__: ClassVar[str] = "AudioPlaybackStarted"


@dataclass(frozen=True)
class AudioPlaybackFinished(Event):
    text: str = ""
    __event_name__: ClassVar[str] = "AudioPlaybackFinished"


@dataclass(frozen=True)
class FrameCaptured(Event):
    width: int = 640
    height: int = 480
    frame_size_bytes: int = 0
    __event_name__: ClassVar[str] = "FrameCaptured"


@dataclass(frozen=True)
class PersonDetected(Event):
    person_id: str = "person_01"
    confidence: float = 0.95
    bounding_box: tuple[int, int, int, int] = (0, 0, 100, 200)
    __event_name__: ClassVar[str] = "PersonDetected"


@dataclass(frozen=True)
class ObjectDetected(Event):
    label: str = "laptop"
    confidence: float = 0.90
    bounding_box: tuple[int, int, int, int] = (10, 10, 50, 50)
    __event_name__: ClassVar[str] = "ObjectDetected"


@dataclass(frozen=True)
class FaceRecognized(Event):
    name: str = "Andres"
    confidence: float = 0.98
    __event_name__: ClassVar[str] = "FaceRecognized"


@dataclass(frozen=True)
class TextRecognized(Event):
    text: str = ""
    confidence: float = 0.90
    __event_name__: ClassVar[str] = "TextRecognized"


@dataclass(frozen=True)
class VisualSceneProcessed(Event):
    objects_count: int = 0
    persons_count: int = 0
    faces_count: int = 0
    __event_name__: ClassVar[str] = "VisualSceneProcessed"


@dataclass(frozen=True)
class EpisodeRecorded(Event):
    episode_id: str = ""
    summary: str = ""
    __event_name__: ClassVar[str] = "EpisodeRecorded"


@dataclass(frozen=True)
class FactLearned(Event):
    fact_id: str = ""
    subject: str = ""
    predicate: str = ""
    object_val: str = ""
    __event_name__: ClassVar[str] = "FactLearned"


@dataclass(frozen=True)
class PreferenceUpdated(Event):
    key: str = ""
    value: str = ""
    __event_name__: ClassVar[str] = "PreferenceUpdated"


@dataclass(frozen=True)
class MemoryConsolidated(Event):
    episodes_consolidated: int = 0
    facts_extracted: int = 0
    __event_name__: ClassVar[str] = "MemoryConsolidated"


@dataclass(frozen=True)
class MemoryQueried(Event):
    query: str = ""
    results_count: int = 0
    __event_name__: ClassVar[str] = "MemoryQueried"


@dataclass(frozen=True)
class ToolRegistered(Event):
    tool_name: str = ""
    category: str = ""
    __event_name__: ClassVar[str] = "ToolRegistered"


@dataclass(frozen=True)
class ToolRequested(Event):
    tool_name: str = ""
    raw_text: str = ""
    __event_name__: ClassVar[str] = "ToolRequested"


@dataclass(frozen=True)
class ToolExecutionStarted(Event):
    tool_name: str = ""
    __event_name__: ClassVar[str] = "ToolExecutionStarted"


@dataclass(frozen=True)
class ToolExecuted(Event):
    tool_name: str = ""
    success: bool = True
    execution_time_ms: float = 0.0
    __event_name__: ClassVar[str] = "ToolExecuted"


@dataclass(frozen=True)
class ToolFailed(Event):
    tool_name: str = ""
    error: str = ""
    __event_name__: ClassVar[str] = "ToolFailed"


@dataclass(frozen=True)
class ToolConfirmationRequired(Event):
    tool_name: str = ""
    risk_level: str = "destructive"
    reason: str = ""
    __event_name__: ClassVar[str] = "ToolConfirmationRequired"


@dataclass(frozen=True)
class MotorMoved(Event):
    joint_id: str = ""
    position: float = 0.0
    __event_name__: ClassVar[str] = "MotorMoved"


@dataclass(frozen=True)
class SensorDataReceived(Event):
    sensor_type: str = ""
    value: float = 0.0
    unit: str = ""
    __event_name__: ClassVar[str] = "SensorDataReceived"


@dataclass(frozen=True)
class NavigationTargetReached(Event):
    waypoint_x: float = 0.0
    waypoint_y: float = 0.0
    __event_name__: ClassVar[str] = "NavigationTargetReached"


@dataclass(frozen=True)
class ObjectManipulated(Event):
    object_id: str = ""
    action: str = "grasp"
    success: bool = True
    __event_name__: ClassVar[str] = "ObjectManipulated"


@dataclass(frozen=True)
class SafetyAlert(Event):
    level: str = "WARNING"
    message: str = ""
    __event_name__: ClassVar[str] = "SafetyAlert"


@dataclass(frozen=True)
class EmergencyStopTriggered(Event):
    reason: str = "user_e_stop"
    __event_name__: ClassVar[str] = "EmergencyStopTriggered"


@dataclass(frozen=True)
class GoalCreated(Event):
    goal_id: str = ""
    description: str = ""
    priority: float = 1.0
    __event_name__: ClassVar[str] = "GoalCreated"


@dataclass(frozen=True)
class GoalStatusChanged(Event):
    goal_id: str = ""
    status: str = "pending"
    __event_name__: ClassVar[str] = "GoalStatusChanged"


@dataclass(frozen=True)
class GoalPrioritized(Event):
    goal_id: str = ""
    priority_score: float = 0.0
    __event_name__: ClassVar[str] = "GoalPrioritized"


@dataclass(frozen=True)
class LongPlanGenerated(Event):
    goal_id: str = ""
    subgoal_count: int = 0
    __event_name__: ClassVar[str] = "LongPlanGenerated"


@dataclass(frozen=True)
class PolicyUpdated(Event):
    policy_name: str = ""
    version: str = "1.0"
    __event_name__: ClassVar[str] = "PolicyUpdated"


@dataclass(frozen=True)
class IntentDetected(Event):
    intent_type: str = "casual_conversation"
    confidence: float = 1.0
    raw_text: str = ""
    __event_name__: ClassVar[str] = "IntentDetected"


@dataclass(frozen=True)
class SessionContextUpdated(Event):
    session_id: str = ""
    current_topic: str = ""
    active_task: str = ""
    last_intent: str = ""
    __event_name__: ClassVar[str] = "SessionContextUpdated"


@dataclass(frozen=True)
class AgentStepEvaluated(Event):
    task_id: str = ""
    plan_id: str = ""
    evaluation_status: str = "SUCCESS"
    reason: str = ""
    __event_name__: ClassVar[str] = "AgentStepEvaluated"


@dataclass(frozen=True)
class AgentConfirmationGranted(Event):
    plan_id: str = ""
    task_id: str = ""
    tool_name: str = ""
    __event_name__: ClassVar[str] = "AgentConfirmationGranted"


@dataclass(frozen=True)
class AgentConfirmationDenied(Event):
    plan_id: str = ""
    task_id: str = ""
    tool_name: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "AgentConfirmationDenied"


@dataclass(frozen=True)
class AgentReplanRequested(Event):
    plan_id: str = ""
    task_id: str = ""
    replan_count: int = 0
    reason: str = ""
    __event_name__: ClassVar[str] = "AgentReplanRequested"


@dataclass(frozen=True)
class AgentReplanned(Event):
    plan_id: str = ""
    task_id: str = ""
    replan_count: int = 0
    new_tasks_count: int = 0
    __event_name__: ClassVar[str] = "AgentReplanned"


@dataclass(frozen=True)
class AgentReplanFailed(Event):
    plan_id: str = ""
    task_id: str = ""
    replan_count: int = 0
    reason: str = ""
    __event_name__: ClassVar[str] = "AgentReplanFailed"


@dataclass(frozen=True)
class AgentPlanCreated(Event):
    plan_id: str = ""
    goal_description: str = ""
    tasks_count: int = 0
    __event_name__: ClassVar[str] = "AgentPlanCreated"


@dataclass(frozen=True)
class AgentPlanCompleted(Event):
    plan_id: str = ""
    completed: bool = True
    failed: bool = False
    waiting_confirmation: bool = False
    steps_executed: int = 0
    duration_ms: float = 0.0
    __event_name__: ClassVar[str] = "AgentPlanCompleted"


@dataclass(frozen=True)
class AgentSecurityAlert(Event):
    event_type: str = "security_alert"
    tool_name: str = ""
    reason: str = ""
    plan_id: str = ""
    task_id: str = ""
    __event_name__: ClassVar[str] = "AgentSecurityAlert"


@dataclass(frozen=True)
class SessionCreated(Event):
    session_id: str = ""
    title: str = "Conversación"
    user_id: str = "default_user"
    __event_name__: ClassVar[str] = "SessionCreated"


@dataclass(frozen=True)
class SessionClosed(Event):
    session_id: str = ""
    __event_name__: ClassVar[str] = "SessionClosed"


@dataclass(frozen=True)
class ConversationTurnStored(Event):
    session_id: str = ""
    turn_id: str = ""
    role: str = "user"
    __event_name__: ClassVar[str] = "ConversationTurnStored"
