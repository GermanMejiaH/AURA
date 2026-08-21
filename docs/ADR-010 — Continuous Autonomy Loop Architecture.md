# ADR-010 — Continuous Autonomy Loop Architecture (AURA 1.6 Stage 4)

## Status
Accepted

## Context
AURA 1.6 Stage 1–3 established temporal schedule domain models (`TemporalSchedule`), SQLite persistence (`ScheduleStore`), pure CRON/interval eligibility evaluation (`ScheduleEvaluator`), and caller-driven execution binding (`ScheduleDispatcher`).
Stage 4 requires an autonomous background runtime loop (`ContinuousAutonomyRuntime`) that periodically triggers schedule evaluation ticks without requiring external manual polling or introducing complex async event loops.

## Decision

1. **Background Periodic Worker (`ContinuousAutonomyRuntime` in `src/aura/cognition/scheduling/runtime.py`)**:
   - Thread-based runtime running a single daemon worker thread (`AuraAutonomyRuntime`).
   - Managed via explicit `start()` and `stop(timeout=5.0)` lifecycle methods (idempotent).
   - Periodically invokes `tick(at_timestamp)` using `_stop_event.wait(tick_interval_seconds)` instead of raw `time.sleep()`.

2. **Clock Abstraction Protocol (`Clock` in `src/aura/cognition/scheduling/clock.py`)**:
   - Defines a clean `Clock` protocol with `SystemClock` for real UTC operations and `TestClock` for controllable unit testing.
   - `TestClock` allows test suites to fast-forward time instantly via `advance(seconds)` without real-world delays.

3. **Overlapping Tick Protection & Single Worker Concurrency**:
   - Uses non-blocking `_tick_lock.acquire(blocking=False)` during each tick. If a goal execution extends beyond the tick interval, overlapping ticks are safely skipped without thread accumulation.

4. **Runtime Observability & Error Recovery**:
   - Publishes `RuntimeStarted`, `RuntimeStopped`, `RuntimeTickCompleted`, and `RuntimeTickFailed` events over `EventBus`.
   - Individual goal or schedule errors do not crash the runtime loop.

## Consequences
- **Positive**: Full continuous autonomous scheduling, deterministic fast-forward unit testing, zero thread explosion, clean event bus integration, 100% backward compatible with AURA 1.5.
- **Negative**: Full system boot auto-start integrated into `AURA.boot()` is deferred to Stage 5.
