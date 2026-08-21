# ADR-015 — Persistent Runtime State & Operational Recovery

## Status
APPROVED AND FROZEN (Stage 9)

## Context
AURA 1.6 Stages 1–8 established temporal scheduling, dispatcher, execution loop, runtime bootstrap, health monitoring, self-recovery, operational telemetry, and a decoupled Control Plane. However, operational runtime state was ephemeral across process lifecycles. If the AURA process exited unexpectedly (due to an OS signal, unhandled exception, power loss, or container termination), the system had no formal persistent state record to distinguish between a clean shutdown and a crash, nor a deterministic policy for post-boot operational recovery.

## Decision
We implement **Stage 9 — Persistent Runtime State & Operational Recovery** as a decoupled, SQLite-backed state persistence and crash recovery architecture:

1. **Decoupled State Persistence (`RuntimeStateStore`)**:
   Provides structured persistence for `PersistentRuntimeSnapshot` using SQLite transactions via `SQLiteMemoryStore`.
   - `save_snapshot(snapshot: PersistentRuntimeSnapshot) -> None`
   - `load_snapshot(runtime_name: str) -> PersistentRuntimeSnapshot | None`
   - `mark_clean_shutdown(runtime_name: str, stopped_at: str | None = None) -> None`
   - `detect_unexpected_shutdown(runtime_name: str) -> bool`

2. **Clean Shutdown vs. Crash Detection**:
   When AURA boots (`AutonomyModule.on_start()`), `RuntimeStateStore` checks whether `clean_shutdown` was set to `1` during previous execution:
   - **Clean Shutdown**: `clean_shutdown == True` or `operational_state == "STOPPED"`. Normal boot sequence proceeds.
   - **Unexpected Shutdown / Crash**: `clean_shutdown == False` and previous `operational_state` in `{"RUNNING", "STARTING", "DEGRADED", "RECOVERING"}`. Emits `RuntimeUnexpectedShutdownDetected`.

3. **Post-Boot Recovery Policy**:
   Upon detecting an unexpected shutdown, `AutonomyModule` evaluates post-boot recovery:
   - `RUNNING` or `STARTING`: Cleanly restarts runtime (`control_plane.start()`) and emits `RuntimePostBootRecoveryAttempted(action="restart")`.
   - `DEGRADED` or `RECOVERING`: Triggers self-recovery (`control_plane.recover()`) within the Stage 6 recovery budget. Emits `RuntimePostBootRecoveryAttempted(action="recover")`.
   - `STOPPED` or `FAILED`: Does NOT auto-recover. Preserves legal stop/failure state to prevent unauthorized execution.

4. **EventBus Integration**:
   Publishes frozen event snapshots:
   - `RuntimeStatePersisted`
   - `RuntimeStateRestored`
   - `RuntimeUnexpectedShutdownDetected`
   - `RuntimePostBootRecoveryAttempted`

5. **IoC Integration**:
   `RuntimeStateStore` is registered in `DependencyContainer` and resolved by `AutonomyModule`.

## Consequences
- **Crash Recovery**: AURA automatically recovers running workloads after unexpected process restarts.
- **Thread & Transaction Safety**: SQLite updates are synchronized with `SQLiteMemoryStore._lock` in atomic transactions.
- **Idempotency & Clean Contracts**: Integrates seamlessly with Stages 1–8 without modifying `ContinuousAutonomyRuntime` core contracts or creating orphan threads.
