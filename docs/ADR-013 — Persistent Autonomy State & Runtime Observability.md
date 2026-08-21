# ADR-013 — Persistent Autonomy State & Runtime Observability

## Status
Approved / Implemented (Stage 7)

## Context
In AURA 1.6 Stages 1 through 6, we designed and implemented a full autonomous scheduling architecture:
- Stage 1: `TemporalSchedule` & `ScheduleStore` (SQLite schedule persistence)
- Stage 2: `ScheduleEvaluator` (pure eligibility engine)
- Stage 3: `ScheduleDispatcher` (synchronous execution binding)
- Stage 4: `ContinuousAutonomyRuntime` & `Clock` (thread-based periodic loop)
- Stage 5: `AutonomyModule` & `AURA.boot()` lifecycle integration
- Stage 6: `HealthMonitor` integration, `RuntimeMetricsSnapshot`, and self-recovery

However, prior to Stage 7, runtime metrics, execution history, and recovery attempts were maintained purely in in-memory state. Upon an AURA application restart or process crash, runtime execution history and recovery statistics were lost, and process crashes left no persistent diagnostic markers.

## Decision
We implement a decoupled, thread-safe, persistent autonomy state and observability layer via `RuntimeHistoryStore` and `RuntimePersistenceHandler` in `aura.cognition.scheduling.persistence`.

### 1. Architectural Principles & Separation of Concerns
We maintain strict decoupling across runtime, persistence, and observability:
- **ContinuousAutonomyRuntime**: Operates purely in-memory (lifecycle, worker thread, ticks, instant metrics). It does NOT depend on SQLite and does NOT wait for DB writes during tick loops.
- **RuntimeHistoryStore**: Manages SQLite storage for durable state (`autonomy_runtime_state`) and event log history (`autonomy_runtime_events`), reusing `SQLiteMemoryStore`.
- **RuntimePersistenceHandler**: Listens asynchronously/synchronously on `EventBus` to record published `Runtime*` events into `RuntimeHistoryStore`. Persistence failures are caught and logged as warnings; they **never** crash runtime execution.
- **AutonomyModule**: Resolves/instantiates `RuntimeHistoryStore` in `on_initialize()`, registers it in `DependencyContainer`, and checks for interrupted runs.

### 2. Database Schema
Reusing AURA's `SQLiteMemoryStore` (`data/aura.db`):
- `autonomy_runtime_state`: Stores single durable state record per runtime (`runtime_name`, `status`, `started_at`, `stopped_at`, `last_tick_at`, `tick_count`, `successful_ticks`, `failed_ticks`, `skipped_overlapping_ticks`, `last_error`, `recovery_attempts_count`, `last_recovery_at`, `recovery_failures_count`, `updated_at`).
- `autonomy_runtime_events`: Stores historical event log (`event_id`, `runtime_name`, `event_type`, `event_timestamp`, `payload_json`, `created_at`). Indexed by `(runtime_name, event_type)` and `event_timestamp`.

### 3. Restart, Rehydration & Crash Detection
- **No Automatic Worker Revival**: Reading a persisted status of `"started"` during `AURA.boot()` does **NOT** automatically spawn a worker thread prior to `on_start()`. The worker loop is driven strictly through normal module lifecycle (`on_start()`).
- **Crash Detection**: `detect_interrupted_run()` compares the last persisted state with the event history. If the last recorded state was `"started"` without a corresponding `"RuntimeStopped"` event, an `InterruptedRunDetected` event is logged to indicate a process crash or unclean shutdown.

### 4. Observability Query API
`RuntimeHistoryStore` provides safe, thread-safe query APIs:
- `get_state(runtime_name)`: Returns latest `RuntimeStateRecord`.
- `get_event_history(runtime_name, limit, event_type)`: Returns filtered event logs (`RuntimeEventRecord`).
- `get_recovery_history(runtime_name, limit)`: Returns historical recovery events.
- `get_failed_ticks(runtime_name, limit)`: Returns historical tick failure events.
- `get_aggregate_stats(runtime_name)`: Returns `RuntimeAggregateStats` (total boots, shutdowns, ticks, recoveries, crashes).
- `prune_events(max_events)`: Auto-prunes events older than `autonomy.history_max_events` (default 1000).

### 5. Configuration Settings
Managed via `ConfigurationManager`:
- `autonomy.persistence_enabled`: bool (default `True`). Master toggle for autonomy state/event persistence.
- `autonomy.history_max_events`: int (default `1000`). Event count threshold for auto-pruning.
- `autonomy.history_retention_days`: int (default `30`). History retention duration.

## Consequences & Backward Compatibility
- **100% Backward Compatible**: All Stage 1–6 contracts (`TemporalSchedule`, `ScheduleEvaluator`, `ScheduleDispatcher`, `ContinuousAutonomyRuntime`, `AutonomyModule`, `HealthMonitor`, self-recovery) remain untouched.
- **High Performance & Resilience**: SQLite operations are atomic and failure-isolated. Database locks or write failures do not affect continuous autonomy tick loops.
