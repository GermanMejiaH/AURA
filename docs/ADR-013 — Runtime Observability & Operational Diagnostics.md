# ADR-013 — Runtime Observability & Operational Diagnostics

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

Prior to Stage 7, inspecting runtime execution state required inspecting raw metrics or internal fields. There was no formal, thread-safe, read-only operational telemetry and diagnostics contract allowing programatic inspection of runtime health, worker thread state, tick metrics, degradation reasons, and recovery attempts.

## Decision
We implement a formal in-memory telemetry and operational diagnostics layer for `ContinuousAutonomyRuntime` via `RuntimeTelemetrySnapshot`, `RuntimeDiagnosticsSnapshot`, `DiagnosticRecord`, `RuntimeDiagnostics`, and diagnostic event notifications in `aura.cognition.scheduling.runtime`.

### 1. Architectural Boundaries & Non-Goals
To prevent scope creep and maintain clean architectural separation:
- **No HTTP/Prometheus/OpenTelemetry**: Stage 7 defines the **internal** telemetry and diagnostics contract of AURA. It does not introduce web dashboards, HTTP endpoints, or external metrics exporters.
- **No Mutability Leaks**: Operational queries return frozen, immutable snapshot objects (`RuntimeTelemetrySnapshot`, `RuntimeDiagnosticsSnapshot`) or safe list copies (`DiagnosticRecord`). No locks, thread references, or mutable objects are exposed.
- **No Generic Logging System**: Stage 7 does not replace Python logging or `EventBus`. It provides bounded, domain-specific telemetry.
- **Read-Only Diagnostics**: `RuntimeDiagnostics` query methods (`get_telemetry()`, `get_snapshot()`, `get_history()`) are strictly read-only and produce zero side effects. They do not start, stop, or recover the runtime.

### 2. Operational Telemetry & Diagnostics Snapshots
We introduce:
- `RuntimeTelemetrySnapshot`: A frozen dataclass encapsulating operational telemetry:
  - `runtime_name: str`
  - `is_running: bool`
  - `thread_alive: bool`
  - `tick_count: int`, `successful_ticks: int`, `failed_ticks: int`, `skipped_overlapping_ticks: int`
  - `last_tick_at: str | None`, `last_successful_tick_at: str | None`, `last_failed_tick_at: str | None`
  - `last_error: str | None`, `started_at: str | None`, `uptime_seconds: float`
  - `recovery_attempts: int`, `successful_recoveries: int`, `failed_recoveries: int`, `last_recovery_at: str | None`
  - `current_health_status: str`, `current_degradation_reason: str | None`

- `RuntimeDiagnosticsSnapshot`: Comprehensive immutable diagnostic snapshot providing full field parity with telemetry and detailed lifecycle timestamps.

- `RuntimeDiagnostics`: Read-only helper interface for programmatically querying runtime state.

Thread-safe snapshots are produced atomically under `_lifecycle_lock` via `runtime.get_telemetry_snapshot()` and `runtime.get_diagnostics_snapshot()`.

### 3. Bounded Diagnostic History
`ContinuousAutonomyRuntime` maintains a bounded in-memory list `_diagnostics_history` of immutable `DiagnosticRecord` entries. The maximum capacity is configured via `autonomy.diagnostics_history_size` (default `50`). Adding new entries beyond capacity pops the oldest entry, preventing unbounded memory growth.

### 4. HealthMonitor Integration
`HealthMonitor` observes autonomy health via `AutonomyModule.get_diagnostics()` or `AutonomyModule.get_telemetry()`. It does **not** directly inspect or manipulate private runtime attributes (`_thread`, `_stop_event`, `_lifecycle_lock`). Self-recovery remains strictly encapsulated within the autonomy runtime.

### 5. Diagnostic Events
We introduce targeted domain events in `aura.events.models`:
- `RuntimeWorkerLost`: Emitted when worker thread loss is detected.
- `RuntimeWorkerRecovered`: Emitted upon successful worker thread self-recovery.
- `RuntimeDiagnosticSnapshotUpdated`: Emitted upon key runtime health state changes.

## Consequences & Backward Compatibility
- **100% Backward Compatible**: All Stage 1–6 contracts (`TemporalSchedule`, `ScheduleEvaluator`, `ScheduleDispatcher`, `ContinuousAutonomyRuntime`, `AutonomyModule`, `HealthMonitor`, self-recovery) remain untouched.
- **Thread Safety**: All snapshot and history access methods acquire `_lifecycle_lock`, guaranteeing thread-safe, lock-free snapshot consumption for concurrent readers.
