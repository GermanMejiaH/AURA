# ADR-007 — Temporal Scheduling Architecture (AURA 1.6 Stage 1)

## Status
Accepted

## Context
AURA 1.5 delivered goal-driven agency with persistent goals, deterministic prioritization, strategic deliberation, execution outcome recording, and goal lifecycle management. However, goals in AURA 1.5 are evaluated on-demand when explicitly triggered.
To progress toward continuous agency and temporal autonomy (AURA 1.6), AURA requires a structured domain representation for temporal schedules (`TemporalSchedule`) and a persistent store (`ScheduleStore`) to track when goals become eligible for execution based on time triggers (timers, intervals, cron patterns, and continuous repetition).

## Decision

1. **Domain Models & Enums (`src/aura/cognition/scheduling/models.py`)**:
   - **`ScheduleType(str, Enum)`**:
     - `ONE_SHOT`: Single execution at a specified target timestamp.
     - `INTERVAL`: Recurring execution every $N$ seconds.
     - `CRON`: Recurring execution according to cron pattern string.
     - `CONTINUOUS`: Immediate re-trigger upon completion of prior run.
   - **`ScheduleStatus(str, Enum)`**:
     - `ACTIVE`: Schedule is enabled and eligible for time evaluation.
     - `PAUSED`: Schedule is temporarily disabled.
     - `COMPLETED`: Schedule finished all planned runs (`ONE_SHOT` or `max_iterations`).
     - `CANCELLED`: Logically cancelled by user/operator.
   - **`TemporalSchedule` Dataclass**:
     - Fields: `schedule_id`, `goal_id`, `schedule_type`, `status`, `expression`, `created_at`, `updated_at`, `last_run_at`, `next_run_at`, `max_iterations`, `iterations_count`, `metadata`.
     - Provides `is_eligible(at_timestamp: str)` deterministic eligibility evaluation without runtime side-effects.

2. **SQLite Persistence (`ScheduleStore` in `src/aura/cognition/scheduling/store.py`)**:
   - Table `temporal_schedules` in SQLite (`data/aura.db`) sharing `SQLiteMemoryStore` connection locking (`threading.RLock`).
   - Indexes on `status`, `schedule_type`, `goal_id`, and `next_run_at`.
   - Foreign key reference to `persistent_goals(goal_id)` with `ON DELETE CASCADE` to clean up associated schedules automatically when a persistent goal is deleted.
   - JSON serialization for `metadata`.
   - Exception safety with fallback defaults for corrupt row parsing.

3. **Separation of Definition vs Evaluation & Execution Scope**:
   - Stage 1 defines and persists schedule definitions (`TemporalSchedule`, `ScheduleStore`) but **does NOT parse or evaluate `INTERVAL` or `CRON` string expressions**.
   - Expression parsing, dynamic calculation of `next_run_at`, and cron string evaluation are explicitly deferred to `ScheduleEvaluator` in Stage 2.
   - `CONTINUOUS` in Stage 1 signifies **purely deterministic eligibility on-demand** (`is_eligible() == True` when `status == ACTIVE`) and **NEVER implies automatic execution**.
   - **No background threads, daemons, asyncio loops, or automatic execution runners** are introduced in Stage 1.
   - Execution runners and runtime schedulers remain strictly deferred to Stage 2+.

4. **Idempotency & Invariants**:
   - Only `ACTIVE` schedules accept execution updates. Attempting to record runs on `PAUSED`, `COMPLETED`, or `CANCELLED` schedules returns safely without mutating state.
   - All timestamps (`created_at`, `updated_at`, `last_run_at`, `next_run_at`) are strictly normalized to UTC ISO 8601 representation (`_normalize_iso_timestamp`).
   - Iteration counts increase monotonically (`iterations_count >= 0`).

## Consequences
- **Positive**: Clean separation of concerns, zero background process overhead in Stage 1, thread-safe SQLite persistence, 100% backward compatible with AURA 1.5.
- **Negative**: Triggering schedule execution requires explicit caller invocation over `ScheduleStore` and `GoalManager` until Stage 2 scheduler runtime is introduced.
