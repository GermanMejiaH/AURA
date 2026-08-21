# ADR-011 — AURA Autonomy Runtime Bootstrap & Lifecycle Integration

## Context

AURA 1.6 Stage 4 introduced `ContinuousAutonomyRuntime`, `Clock`, `SystemClock`, `TestClock`, and runtime lifecycle events (`RuntimeStarted`, `RuntimeStopped`, `RuntimeTickCompleted`, `RuntimeTickFailed`). While Stage 4 established an autonomous thread-based execution engine, the runtime remained caller-driven and was not automatically initialized, started, or stopped during system boot and shutdown.

AURA 1.6 Stage 5 establishes the integration layer connecting `ContinuousAutonomyRuntime` with AURA's core lifecycle (`AURA.boot()` and `AURA.shutdown()`), module management system (`AutonomyModule` & `ModuleManager`), IoC dependency container (`DependencyContainer`), and configuration manager (`ConfigurationManager`).

## Architectural Decisions

### 1. Integration Point & Ownership

- **Ownership**: `AutonomyModule` (`src/aura/autonomy/module.py`) is the primary owner and manager of `ContinuousAutonomyRuntime`, `ScheduleDispatcher`, `ScheduleStore`, and `Clock`.
- **IoC Container Registration**: During `on_initialize()`, `AutonomyModule` registers `ScheduleStore`, `ScheduleDispatcher`, `Clock`, and `ContinuousAutonomyRuntime` into AURA's `DependencyContainer`.
- **Core Boot Sequence Integration**: `AURA.boot()` includes `AutonomyModule` by default in `AURABootOptions` (priority 60). `_step7_initialize_and_start()` triggers module initialization and startup in priority order.

### 2. Lifecycle Integration Flow

```
   AURA.boot()
      │
      ├── Step 2: Load ConfigurationManager (autonomy.tick_interval_seconds=1.0)
      ├── Step 3: Register Core IoC Services
      ├── Step 6: Discover & Load Modules (AutonomyModule)
      └── Step 7: Initialize & Start Modules
            │
            ├── AutonomyModule.on_initialize()
            │     ├── Resolve / Instantiate ScheduleStore, ScheduleDispatcher, Clock
            │     ├── Instantiate ContinuousAutonomyRuntime
            │     └── Register all scheduling services in DependencyContainer
            │
            └── AutonomyModule.on_start()
                  └── ContinuousAutonomyRuntime.start()  ────► [Background Thread 'AuraAutonomyRuntime']
```

```
   AURA.shutdown()
      │
      └── ModuleManager.stop_all() (Reverse Registration Order)
            │
            └── AutonomyModule.on_stop() / on_shutdown()
                  └── ContinuousAutonomyRuntime.stop(timeout=5.0) ──► [Worker Thread Joined Cleanly]
```

### 3. Configuration Management

Configuration keys are managed via `ConfigurationManager`:

- `autonomy.enabled`: bool (default `True`). Master autonomy flag; both `autonomy.enabled` and `autonomy.runtime_enabled` must be `True` for the worker runtime to start.
- `autonomy.tick_interval_seconds`: float (default `1.0`). Clamped to `max(0.05, configured_interval)` in `AutonomyModule.on_initialize()` to prevent busy-waiting.
- `autonomy.runtime_enabled`: bool (default `True`). Specific continuous runtime activation flag.

These settings can be overridden via JSON configuration files, environment variables (`AURA_AUTONOMY_TICK_INTERVAL_SECONDS`), or direct `AURABootOptions`.

### 4. Shutdown & Rollback Safety

- **Idempotent Stopping**: `ContinuousAutonomyRuntime.stop()` is thread-safe and idempotent.
- **Rollback Protection**: If `AURA.boot()` fails during any step, `AURA._rollback_boot()` calls `module_manager.stop_all()`, ensuring that no daemon worker threads remain running.
- **Reverse Shutdown Order**: `ModuleManager.stop_all()` iterates through modules in reverse priority order, stopping `AutonomyModule` before core IoC services are torn down.

## Alternatives Considered

1. **Standalone `AutonomyRuntimeModule`**:
   - *Rejected*: Creating a dedicated module solely for running the scheduling thread would fragment the autonomy subsystem unnecessarily when `AutonomyModule` already encompasses goals, planning, and learning.

2. **Starting Runtime in `AURA._step4_build_support_components()`**:
   - *Rejected*: Support components (e.g., `Scheduler`, `HealthMonitor`) are constructed before domain modules are registered. Starting the runtime in step 4 would prevent `ScheduleDispatcher` from resolving domain dependencies like `AgentPlanner` and `AgentExecutor` from the IoC container.

## Consequences

- `AURA.boot()` automatically starts the continuous autonomy runtime.
- `AURA.shutdown()` cleanly joins background worker threads within 5 seconds.
- `TestClock` can be injected via `AutonomyModule(clock=TestClock(...))` for fast, zero-sleep deterministic integration tests.
- Full backward compatibility with Stage 1–4 is preserved.
