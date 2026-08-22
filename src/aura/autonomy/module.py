from __future__ import annotations

from datetime import UTC, datetime

from ..cognition.goals import GoalManager as CognitionGoalManager
from ..cognition.scheduling import (
    AdaptationStatusSnapshot,
    Clock,
    ContinuousAutonomyRuntime,
    ExecutionStatusSnapshot,
    ExperienceStatusSnapshot,
    GovernanceStatusSnapshot,
    PersistentRuntimeSnapshot,
    PolicyAdaptationEngine,
    PolicyStatusSnapshot,
    RuntimeAdaptationStore,
    RuntimeAdaptivePolicyEngine,
    RuntimeAssuranceEngine,
    RuntimeAssuranceStore,
    RuntimeControlPlane,
    RuntimeExecutionEngine,
    RuntimeExperienceEngine,
    RuntimeExperienceStore,
    RuntimeGovernanceEngine,
    RuntimeHealthSnapshot,
    RuntimeHistoryStore,
    RuntimeOperation,
    RuntimeOrchestrationStore,
    RuntimeOrchestrator,
    RuntimePersistenceHandler,
    RuntimePolicyEngine,
    RuntimeStateStore,
    RuntimeTelemetrySnapshot,
    ScheduleDispatcher,
    ScheduleStore,
    SystemClock,
)
from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import (
    Event,
    EventBus,
    RuntimeHealthChanged,
    RuntimePostBootRecoveryAttempted,
    RuntimeUnexpectedShutdownDetected,
)
from ..logging import get_logger
from ..modules.base import BaseModule, ModuleStatus
from ..tools.registry import ToolRegistry
from .executor import AgentExecutor
from .goals import GoalManager
from .learning import LearningEngine
from .planner import AgentPlanner
from .planning import LongHorizonPlanner
from .prioritization import PriorityEngine


class AutonomyModule(BaseModule):
    """Core module managing autonomous goal prioritization, planning & continuous learning."""

    name = "autonomy"
    description = "Autonomy System - Goal Tracking, Long-Horizon Planning & Learning"
    priority = 60

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        container: DependencyContainer | None = None,
        event_bus: EventBus | None = None,
        goal_manager: GoalManager | None = None,
        priority_engine: PriorityEngine | None = None,
        planner: LongHorizonPlanner | None = None,
        learning_engine: LearningEngine | None = None,
        schedule_store: ScheduleStore | None = None,
        schedule_dispatcher: ScheduleDispatcher | None = None,
        clock: Clock | None = None,
        runtime: ContinuousAutonomyRuntime | None = None,
        history_store: RuntimeHistoryStore | None = None,
        policy_engine: PolicyAdaptationEngine | None = None,
        control_plane: RuntimeControlPlane | None = None,
        state_store: RuntimeStateStore | None = None,
        governance_engine: RuntimeGovernanceEngine | None = None,
        runtime_policy_engine: RuntimePolicyEngine | None = None,
        execution_engine: RuntimeExecutionEngine | None = None,
        experience_store: RuntimeExperienceStore | None = None,
        experience_engine: RuntimeExperienceEngine | None = None,
        adaptation_store: RuntimeAdaptationStore | None = None,
        adaptation_engine: RuntimeAdaptivePolicyEngine | None = None,
        assurance_store: RuntimeAssuranceStore | None = None,
        assurance_engine: RuntimeAssuranceEngine | None = None,
        orchestration_store: RuntimeOrchestrationStore | None = None,
        orchestrator: RuntimeOrchestrator | None = None,
    ) -> None:
        super().__init__(config, container, event_bus)
        self.goals = (
            goal_manager
            if goal_manager is not None
            else GoalManager(event_bus=event_bus, container=container)
        )
        self.priority_engine = priority_engine or PriorityEngine(event_bus=event_bus)
        self.planner = planner or LongHorizonPlanner(event_bus=event_bus)
        self.learning = learning_engine or LearningEngine(event_bus=event_bus)

        self.schedule_store = schedule_store
        self.schedule_dispatcher = schedule_dispatcher
        self.clock = clock
        self.runtime = runtime
        self.history_store = history_store
        self.policy_engine = policy_engine
        self.control_plane = control_plane
        self.state_store = state_store
        self.governance_engine = governance_engine
        self.runtime_policy_engine = runtime_policy_engine
        self.execution_engine = execution_engine
        self.experience_store = experience_store
        self.experience_engine = experience_engine
        self.adaptation_store = adaptation_store
        self.adaptation_engine = adaptation_engine
        self.assurance_store = assurance_store
        self.assurance_engine = assurance_engine
        self.orchestration_store = orchestration_store
        self.orchestrator = orchestrator
        self.persistence_handler: RuntimePersistenceHandler | None = None

    def on_initialize(self) -> None:
        logger = get_logger("AutonomyModule")

        if self.governance_engine is None:
            if self._container is not None and self._container.has(RuntimeGovernanceEngine):
                self.governance_engine = self._container.resolve(RuntimeGovernanceEngine)
            else:
                self.governance_engine = RuntimeGovernanceEngine(
                    clock=self.clock,
                    event_bus=self._event_bus,
                    config=self._config,
                )

        if self.runtime_policy_engine is None:
            if self._container is not None and self._container.has(RuntimePolicyEngine):
                self.runtime_policy_engine = self._container.resolve(RuntimePolicyEngine)
            else:
                self.runtime_policy_engine = RuntimePolicyEngine(
                    clock=self.clock,
                    event_bus=self._event_bus,
                    config=self._config,
                )

        if self.execution_engine is None:
            if self._container is not None and self._container.has(RuntimeExecutionEngine):
                self.execution_engine = self._container.resolve(RuntimeExecutionEngine)
            else:
                self.execution_engine = RuntimeExecutionEngine(
                    clock=self.clock,
                    event_bus=self._event_bus,
                    config=self._config,
                )

        if self.experience_store is None:
            if self._container is not None and self._container.has(RuntimeExperienceStore):
                self.experience_store = self._container.resolve(RuntimeExperienceStore)
            else:
                self.experience_store = RuntimeExperienceStore(container=self._container)

        if self.experience_engine is None:
            if self._container is not None and self._container.has(RuntimeExperienceEngine):
                self.experience_engine = self._container.resolve(RuntimeExperienceEngine)
            else:
                self.experience_engine = RuntimeExperienceEngine(
                    store=self.experience_store,
                    clock=self.clock,
                    event_bus=self._event_bus,
                    config=self._config,
                )

        if self.schedule_store is None:
            if self._container is not None and self._container.has(ScheduleStore):
                self.schedule_store = self._container.resolve(ScheduleStore)
            else:
                self.schedule_store = ScheduleStore(container=self._container)

        if self.schedule_dispatcher is None:
            if self._container is not None and self._container.has(ScheduleDispatcher):
                self.schedule_dispatcher = self._container.resolve(ScheduleDispatcher)
            else:
                planner_inst: AgentPlanner | None = None
                executor_inst: AgentExecutor | None = None
                registry_inst: ToolRegistry | None = None
                cog_goals: CognitionGoalManager | None = None

                if self._container is not None:
                    if self._container.has(AgentPlanner):
                        planner_inst = self._container.resolve(AgentPlanner)
                    if self._container.has(AgentExecutor):
                        executor_inst = self._container.resolve(AgentExecutor)
                    if self._container.has(ToolRegistry):
                        registry_inst = self._container.resolve(ToolRegistry)
                    if self._container.has(CognitionGoalManager):
                        cog_goals = self._container.resolve(CognitionGoalManager)

                if cog_goals is None:
                    cog_goals = CognitionGoalManager(
                        event_bus=self._event_bus, container=self._container
                    )

                self.schedule_dispatcher = ScheduleDispatcher(
                    schedule_store=self.schedule_store,
                    goal_manager=cog_goals,
                    event_bus=self._event_bus,
                    planner=planner_inst,
                    executor=executor_inst,
                    registry=registry_inst,
                    governance_engine=self.governance_engine,
                    policy_engine=self.runtime_policy_engine,
                    execution_engine=self.execution_engine,
                )
        else:
            if self.schedule_dispatcher.governance_engine is None:
                self.schedule_dispatcher.governance_engine = self.governance_engine
            if self.schedule_dispatcher.policy_engine is None:
                self.schedule_dispatcher.policy_engine = self.runtime_policy_engine
            if self.schedule_dispatcher.execution_engine is None:
                self.schedule_dispatcher.execution_engine = self.execution_engine

        if self.clock is None:
            if self._container is not None and self._container.has(Clock):  # type: ignore[arg-type]
                self.clock = self._container.resolve(Clock)  # type: ignore[type-abstract]
            else:
                self.clock = SystemClock()

        interval = 1.0
        if self._config is not None:
            raw_interval = float(
                self._config.get_typed("autonomy.tick_interval_seconds", float, 1.0)
            )
            interval = max(0.05, raw_interval)

        if self.runtime is None:
            if self._container is not None and self._container.has(ContinuousAutonomyRuntime):
                self.runtime = self._container.resolve(ContinuousAutonomyRuntime)
            else:
                self.runtime = ContinuousAutonomyRuntime(
                    dispatcher=self.schedule_dispatcher,
                    clock=self.clock,
                    event_bus=self._event_bus,
                    tick_interval_seconds=interval,
                    runtime_name="AuraAutonomyRuntime",
                )

        persistence_enabled = True
        if self._config is not None:
            persistence_enabled = self._config.get_typed("autonomy.persistence_enabled", bool, True)

        if persistence_enabled:
            if self.history_store is None:
                if self._container is not None and self._container.has(RuntimeHistoryStore):
                    self.history_store = self._container.resolve(RuntimeHistoryStore)
                else:
                    max_ev = 1000
                    if self._config is not None:
                        max_ev = self._config.get_typed("autonomy.history_max_events", int, 1000)
                    self.history_store = RuntimeHistoryStore(
                        container=self._container, max_events=max_ev
                    )

            if (
                self._event_bus is not None
                and self.history_store is not None
                and self.persistence_handler is None
            ):
                self.persistence_handler = RuntimePersistenceHandler(
                    store=self.history_store, event_bus=self._event_bus
                )

            if self.history_store is not None and self.runtime is not None:
                if self.history_store.detect_interrupted_run(self.runtime.runtime_name):
                    name = self.runtime.runtime_name
                    logger.warning(f"Interrupted run detected (runtime='{name}')")
                    self.history_store.record_event(
                        self.runtime.runtime_name,
                        "InterruptedRunDetected",
                        self.clock.now_iso(),
                        {"reason": "unclean_shutdown_or_crash"},
                    )

        if self.policy_engine is None:
            if self._container is not None and self._container.has(PolicyAdaptationEngine):
                self.policy_engine = self._container.resolve(PolicyAdaptationEngine)
            else:
                self.policy_engine = PolicyAdaptationEngine(
                    clock=self.clock,
                    event_bus=self._event_bus,
                    config=self._config,
                )

        if self.runtime is not None and self.runtime.policy_engine is None:
            self.runtime.policy_engine = self.policy_engine

        if self.adaptation_store is None:
            if self._container is not None and self._container.has(RuntimeAdaptationStore):
                self.adaptation_store = self._container.resolve(RuntimeAdaptationStore)
            else:
                self.adaptation_store = RuntimeAdaptationStore(container=self._container)

        if self.adaptation_engine is None:
            if self._container is not None and self._container.has(RuntimeAdaptivePolicyEngine):
                self.adaptation_engine = self._container.resolve(RuntimeAdaptivePolicyEngine)
            else:
                self.adaptation_engine = RuntimeAdaptivePolicyEngine(
                    store=self.adaptation_store,
                    clock=self.clock,
                    event_bus=self._event_bus,
                    config=self._config,
                    experience_engine=self.experience_engine,
                    governance_engine=self.governance_engine,
                    policy_engine=self.runtime_policy_engine,
                )

        if self.assurance_store is None:
            if self._container is not None and self._container.has(RuntimeAssuranceStore):
                self.assurance_store = self._container.resolve(RuntimeAssuranceStore)
            else:
                self.assurance_store = RuntimeAssuranceStore(container=self._container)

        if self.assurance_engine is None:
            if self._container is not None and self._container.has(RuntimeAssuranceEngine):
                self.assurance_engine = self._container.resolve(RuntimeAssuranceEngine)
            else:
                self.assurance_engine = RuntimeAssuranceEngine(
                    store=self.assurance_store,
                    clock=self.clock,
                    event_bus=self._event_bus,
                    config=self._config,
                    governance_engine=self.governance_engine,
                    policy_engine=self.runtime_policy_engine,
                    execution_engine=self.execution_engine,
                    experience_engine=self.experience_engine,
                    adaptation_engine=self.adaptation_engine,
                )

        if self.orchestration_store is None:
            if self._container is not None and self._container.has(RuntimeOrchestrationStore):
                self.orchestration_store = self._container.resolve(RuntimeOrchestrationStore)
            else:
                self.orchestration_store = RuntimeOrchestrationStore(container=self._container)

        if self.orchestrator is None:
            if self._container is not None and self._container.has(RuntimeOrchestrator):
                self.orchestrator = self._container.resolve(RuntimeOrchestrator)
            else:
                self.orchestrator = RuntimeOrchestrator(
                    store=self.orchestration_store,
                    clock=self.clock,
                    event_bus=self._event_bus,
                    config=self._config,
                    governance_engine=self.governance_engine,
                    policy_engine=self.runtime_policy_engine,
                    dispatcher=self.schedule_dispatcher,
                    execution_engine=self.execution_engine,
                    experience_engine=self.experience_engine,
                    adaptation_engine=self.adaptation_engine,
                    assurance_engine=self.assurance_engine,
                )

        if self.control_plane is None and self.runtime is not None:
            if self._container is not None and self._container.has(RuntimeControlPlane):
                self.control_plane = self._container.resolve(RuntimeControlPlane)
            else:
                self.control_plane = RuntimeControlPlane(
                    runtime=self.runtime,
                    clock=self.clock,
                    event_bus=self._event_bus,
                    config=self._config,
                    governance_engine=self.governance_engine,
                    policy_engine=self.runtime_policy_engine,
                    execution_engine=self.execution_engine,
                    experience_engine=self.experience_engine,
                    adaptation_engine=self.adaptation_engine,
                    assurance_engine=self.assurance_engine,
                    orchestrator=self.orchestrator,
                )
        elif self.control_plane is not None:
            if self.control_plane.governance_engine is None:
                self.control_plane.governance_engine = self.governance_engine
            if self.control_plane.policy_engine is None:
                self.control_plane.policy_engine = self.runtime_policy_engine
            if self.control_plane.execution_engine is None:
                self.control_plane.execution_engine = self.execution_engine
            if self.control_plane.experience_engine is None:
                self.control_plane.experience_engine = self.experience_engine
            if self.control_plane.adaptation_engine is None:
                self.control_plane.adaptation_engine = self.adaptation_engine
            if self.control_plane.assurance_engine is None:
                self.control_plane.assurance_engine = self.assurance_engine
            if self.control_plane.orchestrator is None:
                self.control_plane.orchestrator = self.orchestrator

        if self.state_store is None:
            if self._container is not None and self._container.has(RuntimeStateStore):
                self.state_store = self._container.resolve(RuntimeStateStore)
            else:
                self.state_store = RuntimeStateStore(
                    event_bus=self._event_bus, container=self._container
                )

        if self._container is not None:
            self._container.register(GoalManager, instance=self.goals)
            self._container.register(PriorityEngine, instance=self.priority_engine)
            self._container.register(LongHorizonPlanner, instance=self.planner)
            self._container.register(LearningEngine, instance=self.learning)
            self._container.register(ScheduleStore, instance=self.schedule_store)
            self._container.register(ScheduleDispatcher, instance=self.schedule_dispatcher)
            self._container.register(Clock, instance=self.clock)
            self._container.register(ContinuousAutonomyRuntime, instance=self.runtime)
            if self.governance_engine is not None:
                self._container.register(RuntimeGovernanceEngine, instance=self.governance_engine)
            if self.runtime_policy_engine is not None:
                self._container.register(RuntimePolicyEngine, instance=self.runtime_policy_engine)
            if self.execution_engine is not None:
                self._container.register(RuntimeExecutionEngine, instance=self.execution_engine)
            if self.experience_store is not None:
                self._container.register(RuntimeExperienceStore, instance=self.experience_store)
            if self.experience_engine is not None:
                self._container.register(RuntimeExperienceEngine, instance=self.experience_engine)
            if self.adaptation_store is not None:
                self._container.register(RuntimeAdaptationStore, instance=self.adaptation_store)
            if self.adaptation_engine is not None:
                self._container.register(
                    RuntimeAdaptivePolicyEngine, instance=self.adaptation_engine
                )
            if self.assurance_store is not None:
                self._container.register(RuntimeAssuranceStore, instance=self.assurance_store)
            if self.assurance_engine is not None:
                self._container.register(RuntimeAssuranceEngine, instance=self.assurance_engine)
            if self.orchestration_store is not None:
                self._container.register(
                    RuntimeOrchestrationStore, instance=self.orchestration_store
                )
            if self.orchestrator is not None:
                self._container.register(RuntimeOrchestrator, instance=self.orchestrator)
            if self.history_store is not None:
                self._container.register(RuntimeHistoryStore, instance=self.history_store)
            if self.policy_engine is not None:
                self._container.register(PolicyAdaptationEngine, instance=self.policy_engine)
            if self.control_plane is not None:
                self._container.register(RuntimeControlPlane, instance=self.control_plane)
            if self.state_store is not None:
                self._container.register(RuntimeStateStore, instance=self.state_store)

        self.subscribe("GoalSet", self._on_goal_set)
        self.subscribe("GoalAchieved", self._on_goal_achieved)

        logger.info("AutonomyModule initialized")

    def on_start(self) -> None:
        logger = get_logger("AutonomyModule")
        enabled = True
        state_recovery_enabled = True
        state_persistence_enabled = True
        if self._config is not None:
            autonomy_enabled = self._config.get_typed("autonomy.enabled", bool, True)
            runtime_enabled = self._config.get_typed("autonomy.runtime_enabled", bool, True)
            state_recovery_enabled = self._config.get_typed(
                "autonomy.state_recovery_enabled", bool, True
            )
            state_persistence_enabled = self._config.get_typed(
                "autonomy.state_persistence_enabled", bool, True
            )
            enabled = autonomy_enabled and runtime_enabled

        if self.runtime is not None:
            name = self.runtime.runtime_name
            prev_snap = (
                self.state_store.load_snapshot(name)
                if (self.state_store and state_persistence_enabled)
                else None
            )

            if prev_snap is not None and not prev_snap.clean_shutdown:
                prev_state = prev_snap.operational_state
                if self._event_bus:
                    self._event_bus.publish(
                        RuntimeUnexpectedShutdownDetected(
                            runtime_name=name,
                            previous_state=prev_state,
                            detected_at=self.clock.now_iso()
                            if self.clock
                            else datetime.now(UTC).isoformat(),
                        )
                    )
                if state_recovery_enabled:
                    if prev_state in {"RUNNING", "STARTING"}:
                        if self.control_plane:
                            self.control_plane.start()
                        else:
                            self.runtime.start()
                        if self._event_bus:
                            self._event_bus.publish(
                                RuntimePostBootRecoveryAttempted(
                                    runtime_name=name,
                                    previous_state=prev_state,
                                    recovery_action="restart",
                                    success=True,
                                )
                            )
                    elif prev_state in {"DEGRADED", "RECOVERING"}:
                        if self.control_plane:
                            self.control_plane.start()
                        else:
                            self.runtime.start()
                        if self._event_bus:
                            self._event_bus.publish(
                                RuntimePostBootRecoveryAttempted(
                                    runtime_name=name,
                                    previous_state=prev_state,
                                    recovery_action="recover",
                                    success=True,
                                )
                            )
                    else:
                        if self._event_bus:
                            self._event_bus.publish(
                                RuntimePostBootRecoveryAttempted(
                                    runtime_name=name,
                                    previous_state=prev_state,
                                    recovery_action="none_failed_state",
                                    success=False,
                                )
                            )
            elif enabled:
                if self.control_plane:
                    self.control_plane.start()
                else:
                    self.runtime.start()
                logger.info("ContinuousAutonomyRuntime started by AutonomyModule")

            if self.state_store is not None and state_persistence_enabled:
                diag = self.runtime.get_diagnostics_snapshot()
                status_val = (
                    self.control_plane.get_status().value
                    if self.control_plane
                    else diag.health_status
                )
                snap = PersistentRuntimeSnapshot(
                    runtime_name=name,
                    operational_state=status_val,
                    clean_shutdown=False,
                    started_at=diag.started_at,
                    last_tick_at=diag.last_tick_at,
                    last_successful_tick_at=diag.last_successful_tick_at,
                    last_failed_tick_at=diag.last_failed_tick_at,
                    last_error=diag.last_error,
                    recovery_attempts=diag.recovery_attempts,
                    successful_recoveries=diag.recovery_attempts - diag.recovery_failures,
                    failed_recoveries=diag.recovery_failures,
                    last_recovery_at=diag.last_recovery_at,
                    degradation_reason=diag.current_degradation_reason,
                )
                self.state_store.save_snapshot(snap)

    def on_stop(self) -> None:
        logger = get_logger("AutonomyModule")
        if self.runtime is not None:
            if self.control_plane:
                self.control_plane.stop(timeout=5.0)
            elif self.runtime.is_running:
                self.runtime.stop(timeout=5.0)
            if self.state_store is not None:
                self.state_store.mark_clean_shutdown(self.runtime.runtime_name)
            logger.info("ContinuousAutonomyRuntime stopped by AutonomyModule")

    def on_shutdown(self) -> None:
        if self.runtime is not None:
            if self.control_plane:
                self.control_plane.stop(timeout=5.0)
            elif self.runtime.is_running:
                self.runtime.stop(timeout=5.0)
            if self.state_store is not None:
                self.state_store.mark_clean_shutdown(self.runtime.runtime_name)

    def on_health_check(self) -> dict[str, object]:
        if self.runtime is None:
            return {}

        metrics = self.runtime.get_metrics_snapshot()
        health_enabled = True
        recovery_enabled = True
        max_attempts = 3
        backoff_sec = 30.0

        if self._config is not None:
            health_enabled = self._config.get_typed(
                "autonomy.health_monitoring_enabled", bool, True
            )
            recovery_enabled = self._config.get_typed("autonomy.self_recovery_enabled", bool, True)
            max_attempts = self._config.get_typed("autonomy.recovery_max_attempts", int, 3)
            backoff_sec = float(
                self._config.get_typed("autonomy.recovery_backoff_seconds", float, 30.0)
            )

        if health_enabled and metrics.is_running and not metrics.worker_thread_alive:
            logger = get_logger("AutonomyModule")
            logger.warning("ContinuousAutonomyRuntime worker thread died unexpectedly!")
            self._health.status = ModuleStatus.DEGRADED
            self._health.last_error = "worker_thread_dead"

            if self._event_bus:
                self._event_bus.publish(
                    RuntimeHealthChanged(
                        runtime_name=self.runtime.runtime_name,
                        previous_status="HEALTHY",
                        new_status="DEGRADED",
                        reason="worker_thread_dead",
                    )
                )

            if recovery_enabled:
                recovered = self.runtime.recover(
                    reason="worker_thread_dead",
                    max_attempts=max_attempts,
                    backoff_seconds=backoff_sec,
                )
                if recovered:
                    self._health.status = ModuleStatus.RUNNING
                    self._health.last_error = None
                    metrics = self.runtime.get_metrics_snapshot()

        return {
            "tick_count": metrics.tick_count,
            "successful_ticks": metrics.successful_ticks,
            "failed_ticks": metrics.failed_ticks,
            "skipped_overlapping_ticks": metrics.skipped_overlapping_ticks,
            "last_tick_at": metrics.last_tick_at,
            "worker_thread_alive": metrics.worker_thread_alive,
            "is_running": metrics.is_running,
            "uptime_seconds": metrics.uptime_seconds,
        }

    def get_diagnostics(self) -> dict[str, object]:
        """Returns complete diagnostic status from the active continuous autonomy runtime."""
        if self.runtime is None:
            return {"status": "NO_RUNTIME"}
        diag = self.runtime.get_diagnostics_snapshot()
        return {
            "runtime_name": diag.runtime_name,
            "is_running": diag.is_running,
            "worker_thread_alive": diag.worker_thread_alive,
            "thread_name": diag.thread_name,
            "health_status": diag.health_status,
            "tick_count": diag.tick_count,
            "successful_ticks": diag.successful_ticks,
            "failed_ticks": diag.failed_ticks,
            "skipped_overlapping_ticks": diag.skipped_overlapping_ticks,
            "started_at": diag.started_at,
            "last_tick_at": diag.last_tick_at,
            "last_successful_tick_at": diag.last_successful_tick_at,
            "last_failed_tick_at": diag.last_failed_tick_at,
            "uptime_seconds": diag.uptime_seconds,
            "last_error": diag.last_error,
            "recovery_attempts": diag.recovery_attempts,
            "recovery_failures": diag.recovery_failures,
            "last_recovery_at": diag.last_recovery_at,
            "last_state_change_at": diag.last_state_change_at,
            "last_state_change_reason": diag.last_state_change_reason,
        }

    def get_telemetry(self) -> RuntimeTelemetrySnapshot | None:
        """Returns the immutable telemetry snapshot from the active continuous autonomy runtime."""
        if self.runtime is None:
            return None
        return self.runtime.get_telemetry_snapshot()

    def get_runtime_control(self) -> RuntimeControlPlane | None:
        """Returns the active RuntimeControlPlane instance."""
        return self.control_plane

    def get_runtime_status(self) -> str:
        """Returns string representation of current operational status."""
        if self.control_plane is None:
            return "NO_CONTROL_PLANE"
        return self.control_plane.get_status().value

    def get_governance_snapshot(self) -> GovernanceStatusSnapshot | None:
        """Returns the immutable GovernanceStatusSnapshot from governance_engine if available."""
        if self.governance_engine is None:
            return None
        return self.governance_engine.get_governance_snapshot()

    def get_policy_snapshot(self) -> PolicyStatusSnapshot | None:
        """Returns the immutable PolicyStatusSnapshot from runtime_policy_engine if available."""
        if self.runtime_policy_engine is None:
            return None
        return self.runtime_policy_engine.get_policy_snapshot()

    def get_execution_snapshot(self) -> ExecutionStatusSnapshot | None:
        """Returns the immutable ExecutionStatusSnapshot from execution_engine if available."""
        if self.execution_engine is None:
            return None
        return self.execution_engine.get_execution_snapshot()

    def get_experience_snapshot(self) -> ExperienceStatusSnapshot | None:
        """Returns the immutable ExperienceStatusSnapshot from experience_engine if available."""
        if self.experience_engine is None:
            return None
        return self.experience_engine.get_experience_snapshot()

    def get_adaptation_snapshot(self) -> AdaptationStatusSnapshot | None:
        """Returns the immutable AdaptationStatusSnapshot from adaptation_engine if available."""
        if self.adaptation_engine is None:
            return None
        return self.adaptation_engine.get_adaptation_snapshot()

    def get_health_snapshot(self) -> RuntimeHealthSnapshot | None:
        """Returns the immutable RuntimeHealthSnapshot from assurance_engine if available."""
        if self.assurance_engine is None:
            return None
        return self.assurance_engine.get_health_snapshot()

    def get_operation(self, operation_id: str) -> RuntimeOperation | None:
        """Returns the RuntimeOperation from orchestrator if available."""
        if self.orchestrator is None:
            return None
        return self.orchestrator.get_operation(operation_id)

    def _on_goal_set(self, event: Event) -> None:
        desc = getattr(event, "description", "") or event.payload.get("description", "Goal")
        goal = self.goals.create_goal(description=desc)
        self.goals.update_status(goal.goal_id, "active")
        self.planner.generate_plan(goal)
        active = self.goals.get_active_goals()
        self.priority_engine.rank_goals(active)

    def _on_goal_achieved(self, event: Event) -> None:
        goal_id = getattr(event, "goal_id", "") or event.payload.get("goal_id", "")
        if goal_id:
            self.goals.update_status(goal_id, "achieved")
            self.learning.record_feedback(goal_id, success=True)
