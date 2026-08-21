# ADR-014 — Runtime Control Plane & Operational Management

## Status
APPROVED AND FROZEN (Stage 8)

## Context
AURA 1.6 Stages 1–7 established the `ContinuousAutonomyRuntime`, `AutonomyModule`, `HealthMonitor`, and `RuntimeDiagnostics` layer for continuous temporal scheduling, execution, health monitoring, self-recovery, and operational telemetry.

However, operational control over the autonomy runtime was previously scattered or required direct invocation of runtime methods (`start()`, `stop()`, `recover()`). There was no unified, thread-safe, decoupled **Control Plane** that offered structured control commands (`START`, `STOP`, `RESTART`, `RECOVER`), explicit operational state management (`STOPPED`, `STARTING`, `RUNNING`, `DEGRADED`, `RECOVERING`, `STOPPING`, `FAILED`), audit trail history (`ControlAuditEntry`), and full integration with IoC and EventBus without exposing private internal mechanics.

## Decision
We implement **Stage 8 — Runtime Control Plane & Operational Management** as a high-level operational abstraction:

1. **Decoupled Control API (`RuntimeControlPlane`)**:
   Provides structured read/write management over `ContinuousAutonomyRuntime`.
   - `start() -> ControlCommandResult`
   - `stop(timeout=5.0) -> ControlCommandResult`
   - `restart(timeout=5.0) -> ControlCommandResult`
   - `recover(...) -> ControlCommandResult`
   - `get_status() -> RuntimeOperationalState`
   - `get_telemetry() -> RuntimeTelemetrySnapshot`
   - `get_diagnostics() -> RuntimeDiagnosticsSnapshot`
   - `get_history(limit=50) -> list[DiagnosticRecord]`
   - `get_audit_history(limit=100) -> list[ControlAuditEntry]`

2. **Explicit Operational State Model (`RuntimeOperationalState`)**:
   Enumeration defining clean operational states derived deterministically from runtime diagnostics:
   - `STOPPED`: Runtime inactive, worker thread not running.
   - `STARTING`: Initializing worker thread.
   - `RUNNING`: Worker thread active and healthy.
   - `DEGRADED`: Worker thread unresponsive or tick failures occurring while running.
   - `RECOVERING`: Self-recovery attempt in progress.
   - `STOPPING`: Shutdown or stop in progress.
   - `FAILED`: Unrecoverable failure state.

3. **Structured Control Results & Audit Trail (`ControlCommandResult` & `ControlAuditEntry`)**:
   All control operations return frozen dataclasses containing `command`, `success`, `previous_state`, `resulting_state`, `timestamp`, and `message`. A bounded audit log (`autonomy.control_history_size`) records all commands for compliance and diagnostics.

4. **EventBus Integration**:
   Publishes operational control events:
   - `RuntimeControlCommandIssued`
   - `RuntimeControlCommandCompleted`
   - `RuntimeControlCommandFailed`
   - `RuntimeStateChanged`

5. **IoC & AutonomyModule Integration**:
   `AutonomyModule` exposes `get_runtime_control()` and `get_runtime_status()`, registering `RuntimeControlPlane` in `DependencyContainer`.

## Consequences
- **Security & Encapsulation**: Consumers communicate through `RuntimeControlPlane` without inspecting or mutating private fields (`_thread`, `_stop_event`, `_lifecycle_lock`).
- **Idempotency & Thread-Safety**: Commands are synchronized via `RLock`. Redundant commands (`start()` when already running, `stop()` when stopped) succeed cleanly without side-effects or orphan threads.
- **Observability Parity**: Integrates cleanly with Stage 6 Health Monitoring and Stage 7 Diagnostics without duplicating logic or creating extra threads.
