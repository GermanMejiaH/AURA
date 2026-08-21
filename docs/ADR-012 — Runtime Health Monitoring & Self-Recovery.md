# ADR-012 — Runtime Health Monitoring & Self-Recovery

## Status
Approved / Implemented (Stage 6)

## Context
In AURA 1.6 Stage 4 and Stage 5, `ContinuousAutonomyRuntime` introduced a background worker thread (`"AuraAutonomyRuntime"`) that periodically triggers schedule evaluations over `ScheduleDispatcher`. While `ContinuousAutonomyRuntime` and `AutonomyModule` integrate cleanly into `AURA.boot()` and `AURA.shutdown()`, long-running autonomous processes face potential thread degradation (uncaught thread crashes, stuck workers, transient hardware/database faults).

Without active health monitoring and automated recovery, a dead worker thread would leave `ContinuousAutonomyRuntime` in a silent failure state (`is_running == True` but `worker_thread_alive == False`), breaking autonomous schedule execution until manual restart.

## Decision
We implement a lightweight, thread-safe health monitoring, metrics snapshotting, and controlled self-recovery system integrated into `ContinuousAutonomyRuntime`, `AutonomyModule`, and `HealthMonitor`.

### 1. Runtime Metrics (`RuntimeMetricsSnapshot`)
`ContinuousAutonomyRuntime` exposes an immutable snapshot dataclass (`RuntimeMetricsSnapshot`) tracking thread state and tick statistics:
- `runtime_name`: str
- `is_running`: bool
- `worker_thread_alive`: bool
- `tick_count`: int
- `successful_ticks`: int
- `failed_ticks`: int
- `skipped_overlapping_ticks`: int
- `last_tick_at`: str | None
- `last_successful_tick_at`: str | None
- `last_failed_tick_at`: str | None
- `last_error`: str | None
- `started_at`: str | None
- `uptime_seconds`: float

### 2. Health Check & Degradation Detection
`AutonomyModule` implements `on_health_check() -> dict[str, object]`, which is called periodically by AURA's `HealthMonitor`:
- **HEALTHY**: `is_running == True` AND `worker_thread_alive == True`.
- **DEGRADED**: `is_running == True` AND `worker_thread_alive == False` (worker thread died unexpectedly).
- When degradation is detected, `AutonomyModule` updates its status to `ModuleStatus.DEGRADED`, records `last_error = "worker_thread_dead"`, and emits `RuntimeHealthChanged`.

### 3. Anti-Storm Controlled Self-Recovery
When `autonomy.self_recovery_enabled` is `True` and degradation occurs:
1. `ContinuousAutonomyRuntime.recover()` is invoked.
2. The runtime checks its history of recovery attempts within the window defined by `autonomy.recovery_backoff_seconds` (default `30.0`s).
3. If `attempt_number > autonomy.recovery_max_attempts` (default `3`), recovery is aborted to prevent infinite restart loops ("recovery storms"). A `RuntimeRecoveryFailed` event is emitted.
4. Otherwise, `RuntimeRecoveryAttempted` is published, any leftover dead thread is joined cleanly, a new daemon worker thread is spawned, `RuntimeRecovered` is published, and `AutonomyModule` status is restored to `ModuleStatus.RUNNING`.

### 4. Domain Events
Stage 6 introduces four domain events in `aura.events`:
- `RuntimeHealthChanged`: Emitted when runtime status changes (e.g. HEALTHY -> DEGRADED).
- `RuntimeRecoveryAttempted`: Emitted prior to attempting self-recovery.
- `RuntimeRecovered`: Emitted when self-recovery successfully restarts the worker thread.
- `RuntimeRecoveryFailed`: Emitted when self-recovery fails or max attempts are exceeded.

### 5. Configuration Settings
Managed via `ConfigurationManager`:
- `autonomy.health_monitoring_enabled`: bool (default `True`). Enables/disables health monitoring in `AutonomyModule`.
- `autonomy.self_recovery_enabled`: bool (default `True`). Enables/disables auto-recovery during health check.
- `autonomy.recovery_max_attempts`: int (default `3`). Maximum recovery attempts within backoff window.
- `autonomy.recovery_backoff_seconds`: float (default `30.0`). Sliding window duration for anti-recovery storm rate-limiting.

## Consequences & Backward Compatibility
- **100% Backward Compatible**: Stage 1–5 contracts (`TemporalSchedule`, `ScheduleEvaluator`, `ScheduleDispatcher`, `ContinuousAutonomyRuntime` core loops, `AutonomyModule` lifecycle) remain completely unchanged.
- **Zero Orphaned Threads**: `recover()` safely joins old worker threads prior to starting new ones.
- **Thread Safety**: All metrics snapshotting and recovery operations are protected by `ContinuousAutonomyRuntime._lifecycle_lock`.
