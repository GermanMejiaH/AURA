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
    old_status: str = ""
    new_status: str = ""
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
class StrategyDeliberated(Event):
    goal_id: str = ""
    candidates_count: int = 0
    __event_name__: ClassVar[str] = "StrategyDeliberated"


@dataclass(frozen=True)
class StrategySelected(Event):
    goal_id: str = ""
    strategy_id: str = ""
    strategy_name: str = ""
    __event_name__: ClassVar[str] = "StrategySelected"


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
    verification: Any | None = None
    reflection: Any | None = None
    strategy_id: str | None = None
    strategy_name: str | None = None
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


@dataclass(frozen=True)
class PersistentGoalCreated(Event):
    goal_id: str = ""
    description: str = ""
    priority: str = "MEDIUM"
    status: str = "PENDING"
    __event_name__: ClassVar[str] = "PersistentGoalCreated"


@dataclass(frozen=True)
class GoalUpdated(Event):
    goal_id: str = ""
    updated_fields: list[str] = field(default_factory=list)
    __event_name__: ClassVar[str] = "GoalUpdated"


@dataclass(frozen=True)
class GoalProgressUpdated(Event):
    goal_id: str = ""
    completion_percentage: float = 0.0
    milestone_added: str | None = None
    __event_name__: ClassVar[str] = "GoalProgressUpdated"


@dataclass(frozen=True)
class GoalSelectedForExecution(Event):
    goal_id: str = ""
    description: str = ""
    score: float = 0.0
    rank: int = 0
    selection_reason: str = ""
    __event_name__: ClassVar[str] = "GoalSelectedForExecution"


@dataclass(frozen=True)
class GoalOutcomeRecorded(Event):
    goal_id: str = ""
    plan_id: str = ""
    status: str = ""
    completion_percentage: float = 0.0
    strategy_id: str | None = None
    reason: str = ""
    __event_name__: ClassVar[str] = "GoalOutcomeRecorded"


@dataclass(frozen=True)
class ScheduleTriggered(Event):
    schedule_id: str = ""
    goal_id: str = ""
    schedule_type: str = ""
    triggered_at: str = ""
    __event_name__: ClassVar[str] = "ScheduleTriggered"


@dataclass(frozen=True)
class ScheduleRunRecorded(Event):
    schedule_id: str = ""
    goal_id: str = ""
    iterations_count: int = 0
    next_run_at: str | None = None
    status: str = ""
    __event_name__: ClassVar[str] = "ScheduleRunRecorded"


@dataclass(frozen=True)
class ScheduleSkipped(Event):
    schedule_id: str = ""
    goal_id: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "ScheduleSkipped"


@dataclass(frozen=True)
class RuntimeStarted(Event):
    runtime_name: str = ""
    tick_interval: float = 1.0
    started_at: str = ""
    __event_name__: ClassVar[str] = "RuntimeStarted"


@dataclass(frozen=True)
class RuntimeStopped(Event):
    runtime_name: str = ""
    tick_count: int = 0
    stopped_at: str = ""
    __event_name__: ClassVar[str] = "RuntimeStopped"


@dataclass(frozen=True)
class RuntimeTickCompleted(Event):
    tick_index: int = 0
    tick_timestamp: str = ""
    dispatched_count: int = 0
    __event_name__: ClassVar[str] = "RuntimeTickCompleted"


@dataclass(frozen=True)
class RuntimeTickFailed(Event):
    tick_index: int = 0
    tick_timestamp: str = ""
    error: str = ""
    __event_name__: ClassVar[str] = "RuntimeTickFailed"


@dataclass(frozen=True)
class RuntimeHealthChanged(Event):
    runtime_name: str = ""
    previous_status: str = ""
    new_status: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeHealthChanged"


@dataclass(frozen=True)
class RuntimeRecoveryAttempted(Event):
    runtime_name: str = ""
    attempt_number: int = 1
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeRecoveryAttempted"


@dataclass(frozen=True)
class RuntimeRecovered(Event):
    runtime_name: str = ""
    attempt_number: int = 1
    recovered_at: str = ""
    __event_name__: ClassVar[str] = "RuntimeRecovered"


@dataclass(frozen=True)
class RuntimeRecoveryFailed(Event):
    runtime_name: str = ""
    attempt_number: int = 1
    reason: str = ""
    recovery_id: str = ""
    __event_name__: ClassVar[str] = "RuntimeRecoveryFailed"


@dataclass(frozen=True)
class RuntimeWorkerLost(Event):
    runtime_name: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeWorkerLost"


@dataclass(frozen=True)
class RuntimeWorkerRecovered(Event):
    runtime_name: str = ""
    attempt_number: int = 1
    recovered_at: str = ""
    __event_name__: ClassVar[str] = "RuntimeWorkerRecovered"


@dataclass(frozen=True)
class RuntimeDiagnosticSnapshotUpdated(Event):
    runtime_name: str = ""
    health_status: str = ""
    __event_name__: ClassVar[str] = "RuntimeDiagnosticSnapshotUpdated"


@dataclass(frozen=True)
class RuntimePolicyChanged(Event):
    runtime_name: str = ""
    previous_activity_level: str = ""
    new_activity_level: str = ""
    effective_tick_interval: float = 1.0
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimePolicyChanged"


@dataclass(frozen=True)
class RuntimeActivityLevelChanged(Event):
    runtime_name: str = ""
    previous_level: str = ""
    new_level: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeActivityLevelChanged"


@dataclass(frozen=True)
class RuntimeControlCommandIssued(Event):
    command: str = ""
    command_timestamp: str = ""
    __event_name__: ClassVar[str] = "RuntimeControlCommandIssued"


@dataclass(frozen=True)
class RuntimeControlCommandCompleted(Event):
    command: str = ""
    success: bool = True
    previous_state: str = ""
    resulting_state: str = ""
    __event_name__: ClassVar[str] = "RuntimeControlCommandCompleted"


@dataclass(frozen=True)
class RuntimeControlCommandFailed(Event):
    command: str = ""
    error: str = ""
    previous_state: str = ""
    __event_name__: ClassVar[str] = "RuntimeControlCommandFailed"


@dataclass(frozen=True)
class RuntimeStateChanged(Event):
    previous_state: str = ""
    new_state: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeStateChanged"


@dataclass(frozen=True)
class RuntimeStatePersisted(Event):
    runtime_name: str = ""
    operational_state: str = ""
    clean_shutdown: bool = False
    __event_name__: ClassVar[str] = "RuntimeStatePersisted"


@dataclass(frozen=True)
class RuntimeStateRestored(Event):
    runtime_name: str = ""
    restored_state: str = ""
    clean_shutdown: bool = False
    __event_name__: ClassVar[str] = "RuntimeStateRestored"


@dataclass(frozen=True)
class RuntimeUnexpectedShutdownDetected(Event):
    runtime_name: str = ""
    previous_state: str = ""
    detected_at: str = ""
    __event_name__: ClassVar[str] = "RuntimeUnexpectedShutdownDetected"


@dataclass(frozen=True)
class RuntimePostBootRecoveryAttempted(Event):
    runtime_name: str = ""
    previous_state: str = ""
    recovery_action: str = ""
    success: bool = True
    __event_name__: ClassVar[str] = "RuntimePostBootRecoveryAttempted"


@dataclass(frozen=True)
class AutonomyScopeChanged(Event):
    runtime_name: str = ""
    previous_scope: str = ""
    new_scope: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "AutonomyScopeChanged"


@dataclass(frozen=True)
class CircuitBreakerTripped(Event):
    target_id: str = ""
    failure_count: int = 0
    cooloff_seconds: float = 60.0
    reason: str = ""
    __event_name__: ClassVar[str] = "CircuitBreakerTripped"


@dataclass(frozen=True)
class CircuitBreakerReset(Event):
    target_id: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "CircuitBreakerReset"


@dataclass(frozen=True)
class GovernanceExecutionBlocked(Event):
    action_id: str = ""
    reason: str = ""
    scope: str = ""
    circuit_state: str = ""
    __event_name__: ClassVar[str] = "GovernanceExecutionBlocked"


@dataclass(frozen=True)
class RuntimePolicyDecisionMade(Event):
    task_id: str = ""
    action: str = ""
    reason: str = ""
    effective_priority: float = 0.0
    decision_timestamp: str = ""
    __event_name__: ClassVar[str] = "RuntimePolicyDecisionMade"


@dataclass(frozen=True)
class RuntimePolicyConflictDetected(Event):
    conflict_id: str = ""
    conflict_type: str = ""
    winning_task_id: str = ""
    losing_task_id: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimePolicyConflictDetected"


@dataclass(frozen=True)
class RuntimeTaskDeferred(Event):
    task_id: str = ""
    reason: str = ""
    effective_priority: float = 0.0
    __event_name__: ClassVar[str] = "RuntimeTaskDeferred"


@dataclass(frozen=True)
class RuntimeTaskCancelled(Event):
    task_id: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeTaskCancelled"


@dataclass(frozen=True)
class RuntimeTaskPriorityChanged(Event):
    task_id: str = ""
    previous_priority: float = 0.0
    new_priority: float = 0.0
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeTaskPriorityChanged"


@dataclass(frozen=True)
class RuntimeExecutionStarted(Event):
    execution_id: str = ""
    goal_id: str = ""
    schedule_id: str = ""
    idempotency_key: str = ""
    attempt_number: int = 1
    __event_name__: ClassVar[str] = "RuntimeExecutionStarted"


@dataclass(frozen=True)
class RuntimeExecutionValidated(Event):
    execution_id: str = ""
    goal_id: str = ""
    __event_name__: ClassVar[str] = "RuntimeExecutionValidated"


@dataclass(frozen=True)
class RuntimeExecutionCompleted(Event):
    execution_id: str = ""
    goal_id: str = ""
    state: str = ""
    __event_name__: ClassVar[str] = "RuntimeExecutionCompleted"


@dataclass(frozen=True)
class RuntimeExecutionFailed(Event):
    execution_id: str = ""
    goal_id: str = ""
    error: str = ""
    failure_type: str = ""
    __event_name__: ClassVar[str] = "RuntimeExecutionFailed"


@dataclass(frozen=True)
class RuntimeExecutionRetrying(Event):
    execution_id: str = ""
    attempt_number: int = 1
    max_attempts: int = 3
    error: str = ""
    __event_name__: ClassVar[str] = "RuntimeExecutionRetrying"


@dataclass(frozen=True)
class RuntimeExecutionRolledBack(Event):
    execution_id: str = ""
    reason: str = ""
    success: bool = True
    __event_name__: ClassVar[str] = "RuntimeExecutionRolledBack"


@dataclass(frozen=True)
class RuntimeExecutionCompensating(Event):
    execution_id: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeExecutionCompensating"


@dataclass(frozen=True)
class RuntimeExecutionCompensated(Event):
    execution_id: str = ""
    reason: str = ""
    success: bool = True
    __event_name__: ClassVar[str] = "RuntimeExecutionCompensated"


@dataclass(frozen=True)
class RuntimeExecutionCancelled(Event):
    execution_id: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeExecutionCancelled"


@dataclass(frozen=True)
class RuntimeExecutionTimedOut(Event):
    execution_id: str = ""
    timeout_seconds: float = 0.0
    __event_name__: ClassVar[str] = "RuntimeExecutionTimedOut"


@dataclass(frozen=True)
class RuntimeOutcomeRecorded(Event):
    execution_id: str = ""
    action_id: str = ""
    outcome_type: str = ""
    success: bool = True
    __event_name__: ClassVar[str] = "RuntimeOutcomeRecorded"


@dataclass(frozen=True)
class RuntimeExperienceUpdated(Event):
    action_id: str = ""
    total_executions: int = 0
    success_rate: float = 0.0
    confidence: str = ""
    __event_name__: ClassVar[str] = "RuntimeExperienceUpdated"


@dataclass(frozen=True)
class RuntimeRecommendationGenerated(Event):
    action_id: str = ""
    recommendation_type: str = ""
    confidence: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeRecommendationGenerated"


@dataclass(frozen=True)
class RuntimeFailurePatternDetected(Event):
    action_id: str = ""
    pattern_type: str = ""
    details: str = ""
    __event_name__: ClassVar[str] = "RuntimeFailurePatternDetected"


@dataclass(frozen=True)
class RuntimeOperatorReviewRecommended(Event):
    action_id: str = ""
    reason: str = ""
    consecutive_failures: int = 0
    failure_rate: float = 0.0
    __event_name__: ClassVar[str] = "RuntimeOperatorReviewRecommended"


@dataclass(frozen=True)
class RuntimeAdaptationProposed(Event):
    proposal_id: str = ""
    action_id: str = ""
    adaptation_type: str = ""
    proposed_value: str = ""
    requires_operator_approval: bool = True
    __event_name__: ClassVar[str] = "RuntimeAdaptationProposed"


@dataclass(frozen=True)
class RuntimeAdaptationValidationPassed(Event):
    proposal_id: str = ""
    action_id: str = ""
    __event_name__: ClassVar[str] = "RuntimeAdaptationValidationPassed"


@dataclass(frozen=True)
class RuntimeAdaptationValidationFailed(Event):
    proposal_id: str = ""
    action_id: str = ""
    violations: list[str] = field(default_factory=list)
    __event_name__: ClassVar[str] = "RuntimeAdaptationValidationFailed"


@dataclass(frozen=True)
class RuntimeAdaptationApproved(Event):
    proposal_id: str = ""
    action_id: str = ""
    operator_id: str = ""
    __event_name__: ClassVar[str] = "RuntimeAdaptationApproved"


@dataclass(frozen=True)
class RuntimeAdaptationRejected(Event):
    proposal_id: str = ""
    action_id: str = ""
    operator_id: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeAdaptationRejected"


@dataclass(frozen=True)
class RuntimeAdaptationApplied(Event):
    proposal_id: str = ""
    action_id: str = ""
    applied_value: str = ""
    __event_name__: ClassVar[str] = "RuntimeAdaptationApplied"


@dataclass(frozen=True)
class RuntimeAdaptationRolledBack(Event):
    proposal_id: str = ""
    action_id: str = ""
    restored_value: str = ""
    __event_name__: ClassVar[str] = "RuntimeAdaptationRolledBack"


@dataclass(frozen=True)
class RuntimeAdaptationExpired(Event):
    proposal_id: str = ""
    action_id: str = ""
    __event_name__: ClassVar[str] = "RuntimeAdaptationExpired"


@dataclass(frozen=True)
class RuntimeAdaptationBlocked(Event):
    proposal_id: str = ""
    action_id: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeAdaptationBlocked"


@dataclass(frozen=True)
class RuntimeHealthStatusChanged(Event):
    previous_status: str = ""
    new_status: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeHealthStatusChanged"


@dataclass(frozen=True)
class RuntimeInvariantViolationDetected(Event):
    violation_id: str = ""
    invariant_id: str = ""
    severity: str = ""
    component: str = ""
    description: str = ""
    __event_name__: ClassVar[str] = "RuntimeInvariantViolationDetected"


@dataclass(frozen=True)
class RuntimeAuditRecorded(Event):
    audit_id: str = ""
    correlation_id: str = ""
    component: str = ""
    stage: str = ""
    event_type: str = ""
    severity: str = ""
    __event_name__: ClassVar[str] = "RuntimeAuditRecorded"


@dataclass(frozen=True)
class RuntimeCheckpointCreated(Event):
    checkpoint_id: str = ""
    reason: str = ""
    event_timestamp: str = ""
    __event_name__: ClassVar[str] = "RuntimeCheckpointCreated"


@dataclass(frozen=True)
class RuntimeRecoveryStarted(Event):
    recovery_id: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeRecoveryStarted"


@dataclass(frozen=True)
class RuntimeRecoveryCompleted(Event):
    recovery_id: str = ""
    restored_components: tuple[str, ...] = ()
    __event_name__: ClassVar[str] = "RuntimeRecoveryCompleted"


@dataclass(frozen=True)
class RuntimeSafeModeEntered(Event):
    reason: str = ""
    event_timestamp: str = ""
    __event_name__: ClassVar[str] = "RuntimeSafeModeEntered"


@dataclass(frozen=True)
class RuntimeSafeModeExited(Event):
    reason: str = ""
    event_timestamp: str = ""
    __event_name__: ClassVar[str] = "RuntimeSafeModeExited"


@dataclass(frozen=True)
class RuntimeComponentDegraded(Event):
    component: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeComponentDegraded"


@dataclass(frozen=True)
class RuntimeOperationStarted(Event):
    operation_id: str = ""
    correlation_id: str = ""
    goal_id: str = ""
    action_id: str = ""
    __event_name__: ClassVar[str] = "RuntimeOperationStarted"


@dataclass(frozen=True)
class RuntimeOperationStateChanged(Event):
    operation_id: str = ""
    previous_state: str = ""
    new_state: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeOperationStateChanged"


@dataclass(frozen=True)
class RuntimeOperationCompleted(Event):
    operation_id: str = ""
    execution_id: str = ""
    duration: float = 0.0
    __event_name__: ClassVar[str] = "RuntimeOperationCompleted"


@dataclass(frozen=True)
class RuntimeOperationFailed(Event):
    operation_id: str = ""
    reason: str = ""
    failure_type: str = ""
    __event_name__: ClassVar[str] = "RuntimeOperationFailed"


@dataclass(frozen=True)
class RuntimeOperationCancelled(Event):
    operation_id: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeOperationCancelled"


@dataclass(frozen=True)
class RuntimeOperationBlocked(Event):
    operation_id: str = ""
    reason: str = ""
    blocking_stage: str = ""
    __event_name__: ClassVar[str] = "RuntimeOperationBlocked"


@dataclass(frozen=True)
class RuntimeOperationRecoveryRequired(Event):
    operation_id: str = ""
    reason: str = ""
    __event_name__: ClassVar[str] = "RuntimeOperationRecoveryRequired"
