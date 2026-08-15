# ADR-008 — Temporal Schedule Evaluator Architecture (AURA 1.6 Stage 2)

## Status
Accepted

## Context
AURA 1.6 Stage 1 implemented `TemporalSchedule` domain models and `ScheduleStore` for SQLite persistence. However, Stage 1 explicitly avoided calculating dynamic execution timestamps (`next_run_at`), parsing `INTERVAL` or `CRON` expressions, or modifying schedule state.
Stage 2 requires a dedicated, pure, and deterministic evaluation engine (`ScheduleEvaluator`) to assess schedule eligibility at any given time and compute the next target execution timestamp (`next_run_at`) without modifying database state or introducing background daemons/runners.

## Decision

1. **Pure & Deterministic Evaluation Engine (`ScheduleEvaluator` in `src/aura/cognition/scheduling/evaluator.py`)**:
   - `ScheduleEvaluator` is a pure functional component. Given a `TemporalSchedule` and a reference timestamp `at_timestamp`, it returns an immutable `EvaluationResult` without mutating the database or schedule object.
   - Zero side-effects: `ScheduleEvaluator` does NOT access SQLite, does NOT call `ScheduleStore.save_schedule()`, and does NOT trigger `AgentExecutor`.

2. **Immutable Result Data Structure (`EvaluationResult`)**:
   - `is_eligible`: Boolean indicating if the schedule is currently eligible for execution.
   - `schedule_id`: ID of evaluated schedule.
   - `goal_id`: ID of target goal.
   - `current_status`: Status at time of evaluation.
   - `next_status`: Suggested status after execution (e.g. `COMPLETED` when `max_iterations` reached or `ONE_SHOT` finishes).
   - `calculated_next_run_at`: Next UTC ISO 8601 timestamp after run execution.
   - `reason`: Human-readable explanation of eligibility decision.

3. **Type-Specific Semantics**:
   - **`ONE_SHOT`**: Eligible if `status == ACTIVE`, `iterations_count == 0`, and `next_run_at <= at_timestamp`. After run, `calculated_next_run_at` is `None` and `next_status` is `COMPLETED`.
   - **`INTERVAL`**: Expression is interval $N$ in seconds (e.g., `"300"` for 5 minutes). Eligible if `next_run_at <= at_timestamp`. Overdue handling: `calculated_next_run_at` jumps forward relative to `at_timestamp` (`at_timestamp + N seconds`) to prevent infinite catch-up loops when multiple intervals were missed.
   - **`CRON`**: Explicit standard 5-field cron subset (`minute`: 0-59, `hour`: 0-23, `dom`: 1-31, `month`: 1-12, `dow`: 0-6 with 7 mapping to 0 Sunday). Evaluated via a pure-Python cron parser without external dependencies. Supports `*`, `*/N`, `A-B`, `A-B/N`, and comma lists. Non-5-field expressions, inverted ranges (`15-5`), or invalid steps (`*/0`) fall back safely to valid ranges or default intervals without raising exceptions or looping infinitely. Macro extensions (e.g. `@reboot`) are explicitly out of scope.
   - **`CONTINUOUS`**: Eligible whenever `status == ACTIVE` and `iterations_count < max_iterations`. `calculated_next_run_at` is `at_timestamp`. Signifies immediate eligibility on-demand, **never automatic background execution**.

4. **Status & Limit Invariants**:
   - Schedules in `PAUSED`, `COMPLETED`, or `CANCELLED` status are strictly non-eligible (`is_eligible = False`).
   - Schedules reaching `iterations_count >= max_iterations` return `is_eligible = False` and `next_status = COMPLETED`.

5. **UTC Timezone Handling**:
   - All input timestamps are converted to UTC ISO 8601 strings. Naïve datetimes are treated as UTC.

## Consequences
- **Positive**: 100% deterministic, zero external dependencies, 100% pure evaluation without side-effects, thread-safe, ready for Stage 3 scheduler integration.
- **Negative**: Cron parsing is limited to standard 5-field syntax without extended non-standard macro extensions (e.g. `@reboot`).
