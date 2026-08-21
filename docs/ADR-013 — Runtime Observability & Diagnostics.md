# ADR-013 — Runtime Observability & Diagnostics

## Status
Approved / Implemented (Stage 7)

## Context
In AURA 1.6 Stages 1 through 6, we designed and implemented a full autonomous scheduling architecture:
- Stage 1: `TemporalSchedule` & `ScheduleStore`
- Stage 2: `ScheduleEvaluator`
- Stage 3: `ScheduleDispatcher`
- Stage 4: `ContinuousAutonomyRuntime` & `Clock`
- Stage 5: `AutonomyModule` & `AURA.boot()` lifecycle integration
- Stage 6: `HealthMonitor` integration, `RuntimeMetricsSnapshot`, and self-recovery

However, diagnostic inspection of runtime execution state previously required inspecting raw internal metrics or private thread/lock properties. There was no formal, thread-safe, immutable diagnostic snapshot representing complete runtime health, worker thread state, diagnostic history, or state change reasons.

## Decision
We implement a formal in-memory diagnostic observability contract for `ContinuousAutonomyRuntime` via `RuntimeDiagnosticsSnapshot`, `DiagnosticRecord`, and diagnostic event notifications in `aura.cognition.scheduling.runtime`.

### 1. Architectural Boundaries & Non-Goals
To prevent scope creep and maintain clean architectural separation:
- **No HTTP/Prometheus/OpenTelemetry**: Stage 7 defines the **internal** observability contract of AURA. It does not introduce web dashboards, HTTP endpoints, or external metrics exporters.
- **No Mutability Leaks**: Diagnostic queries return frozen, immutable snapshot objects (`RuntimeDiagnosticsSnapshot`) or safe list copies (`DiagnosticRecord`). No locks, thread references, or mutable objects are exposed.
- **No Generic Logging System**: Stage 7 does not replace Python logging or `EventBus`. It provides bounded, domain-specific telemetry.

### 2. Runtime Diagnostics Snapshot
We introduce `RuntimeDiagnosticsSnapshot`, a frozen dataclass containing:
- `runtime_name: str`
- `is_running: bool`
- `worker_thread_alive: bool`
- `thread_name: str | None`
- `tick_count: int`, `successful_ticks: int`, `failed_ticks: int`, `skipped_overlapping_ticks: int`
- `started_at: str | None`, `last_tick_at: str | None`, `last_successful_tick_at: str | None`, `last_failed_tick_at: str | None`
- `uptime_seconds: float`
- `last_error: str | None`
- `health_status: str` (`HEALTHY`, `DEGRADED`, `STOPPED`)
- `recovery_attempts: int`, `recovery_failures: int`, `last_recovery_at: str | None`
- `last_state_change_at: str | None`, `last_state_change_reason: str | None`

Thread-safe snapshots are produced atomically under `_lifecycle_lock` via `runtime.get_diagnostics_snapshot()`.

### 3. Bounded Diagnostic History
`ContinuousAutonomyRuntime` maintains a bounded in-memory list `_diagnostics_history` of immutable `DiagnosticRecord` entries. The maximum capacity is configured via `autonomy.diagnostics_history_size` (default `50`). Adding new entries beyond capacity pops the oldest entry, preventing unbounded memory growth.

### 4. HealthMonitor Integration
`HealthMonitor` observes autonomy health via `AutonomyModule.get_diagnostics()` or `AutonomyModule.on_health_check()`. It does **not** directly inspect or manipulate private runtime attributes (`_thread`, `_stop_event`, `_lifecycle_lock`). Self-recovery remains strictly encapsulated within the autonomy runtime.

### 5. Diagnostic Events
We introduce targeted domain events in `aura.events.models`:
- `RuntimeWorkerLost`: Emitted when worker thread loss is detected.
- `RuntimeWorkerRecovered`: Emitted upon successful worker thread self-recovery.
- `RuntimeDiagnosticSnapshotUpdated`: Emitted upon key runtime health state changes.

## Consequences & Backward Compatibility
- **100% Backward Compatible**: All Stage 1–6 contracts (`TemporalSchedule`, `ScheduleEvaluator`, `ScheduleDispatcher`, `ContinuousAutonomyRuntime`, `AutonomyModule`, `HealthMonitor`, self-recovery) remain untouched.
- **Thread Safety**: All snapshot and history access methods acquire `_lifecycle_lock`, guaranteeing thread-safe, lock-free snapshot consumption for concurrent readers.
