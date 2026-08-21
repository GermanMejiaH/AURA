# ADR-014 — Policy & Priority Adaptation Engine

## Status
Approved / Implemented (Stage 8)

## Context
In AURA 1.6 Stages 1 through 7, we built the core continuous autonomy runtime, lifecycle integration, health monitoring, self-recovery, state persistence, and diagnostic telemetry:
- Stage 1: `TemporalSchedule` & `ScheduleStore`
- Stage 2: `ScheduleEvaluator`
- Stage 3: `ScheduleDispatcher`
- Stage 4: `ContinuousAutonomyRuntime` & `Clock`
- Stage 5: `AutonomyModule` & `AURA.boot()` lifecycle integration
- Stage 6: `HealthMonitor` integration & worker self-recovery
- Stage 7: `RuntimeDiagnosticsSnapshot` & state persistence

Prior to Stage 8, the runtime executed at a fixed tick interval (`tick_interval_seconds`) regardless of system load, health degraded states, or worker recovery events.

## Decision
We introduce `PolicyAdaptationEngine` in `aura.cognition.scheduling.policy` to deterministically adjust operational runtime behavior (`effective_tick_interval_seconds`, `ActivityLevel`, `PriorityMode`) based on observable operational signals (`SystemSignals`).

### 1. Architectural Boundaries & Non-Goals
- **No Complex Heuristics**: Policy evaluation is strictly deterministic and rule-based. It does not introduce ML models or opaquely trained heuristics.
- **No Agent Planner Intrusion**: Stage 8 only adjusts operational frequency and activity throttling; it does not modify goal selection logic, `AgentPlanner`, or `AgentExecutor`.
- **No Self-Recovery Duplication**: Self-recovery remains the sole responsibility of Stage 6 (`runtime.recover()`). The policy engine observes recovery states to throttle activity, but does not initiate worker thread resurrection.

### 2. Operational Activity Levels
`ActivityLevel` represents operational state throttling:
- `NORMAL`: Standard autonomous operation using configured tick interval.
- `REDUCED`: Throttled activity (multiplied tick interval, `PriorityMode.THROTTLED`) triggered by `DEGRADED` health, high load, or recovery attempts.
- `SUSPENDED`: Minimal activity (`PriorityMode.CRITICAL_ONLY`, max interval) triggered by `STOPPED` runtime, worker loss, or recovery failures.

### 3. Effective Tick Interval Adaptation
- `configured_tick_interval_seconds`: The source of truth configured in `ConfigurationManager` (`autonomy.tick_interval_seconds`).
- `effective_tick_interval_seconds`: Dynamically calculated by `PolicyAdaptationEngine.evaluate_policy()` and consumed by `ContinuousAutonomyRuntime._worker_loop()`.
- All calculated intervals are strictly clamped to `[autonomy.min_tick_interval_seconds, autonomy.max_tick_interval_seconds]`. Invalid values (NaN, Inf, $\le 0$) are sanitized safely to defaults.

### 4. Diagnostic Events
- `RuntimePolicyChanged`: Emitted when the runtime policy decision or effective tick interval changes.
- `RuntimeActivityLevelChanged`: Emitted when `ActivityLevel` transitions between `NORMAL`, `REDUCED`, or `SUSPENDED`.

## Consequences & Backward Compatibility
- **100% Backward Compatible**: If `autonomy.adaptation_enabled` is `False` or no `policy_engine` is configured, `ContinuousAutonomyRuntime` preserves its original fixed tick behavior.
- **Thread Safety**: All policy evaluations and event emissions are synchronized under `_lock`, preventing race conditions during concurrent reader/writer access.
