# ADR-009 — Temporal Schedule Dispatcher & Execution Binding (AURA 1.6 Stage 3)

## Status
Accepted

## Context
AURA 1.6 Stage 1 implemented `TemporalSchedule` domain models and `ScheduleStore` for SQLite persistence. Stage 2 introduced `ScheduleEvaluator` for pure, deterministic eligibility calculation.
Stage 3 requires a synchronous dispatcher (`ScheduleDispatcher`) to bind due schedules to their associated `PersistentGoal` execution cycles and persist updated execution counts, timestamps, and status changes in SQLite without introducing background daemons, threads, or asyncio loops.

## Decision

1. **Synchronous, Caller-Driven Dispatcher (`ScheduleDispatcher` in `src/aura/cognition/scheduling/dispatcher.py`)**:
   - `ScheduleDispatcher` binds `TemporalSchedule` instances from `ScheduleStore` to `GoalManager` and execution pipelines (`AgentPlanner`, `AgentExecutor`).
   - Exposed via `process_due_schedules(at_timestamp: str | None = None, execute_goals: bool = True) -> list[DispatchResult]`.
   - Purely synchronous and caller-driven. **No background daemons, threads, asyncio loops, or `sleep()` calls are introduced.**

2. **Execution Flow & Goal Association**:
   - Queries eligible schedules from `ScheduleStore.list_eligible_schedules(at_timestamp)`.
   - Re-evaluates eligibility via `ScheduleEvaluator`.
   - Verifies target goal via `GoalManager.get_goal(goal_id)`. If goal is missing, cancelled, completed, failed, or paused, emits `ScheduleSkipped` and does NOT consume schedule runs.
   - If `execute_goals=True`, executes the specific target goal via `AgentPlanner` / `AgentExecutor` and records outcome via `GoalManager.record_execution_outcome()`.
   - Updates schedule via `sched.record_run()` and persists changes via `ScheduleStore.save_schedule()`.

3. **Dry-Run Inspection Mode (`execute_goals=False`)**:
   - Performs eligibility inspection and simulation without calling `planner`, `executor`, `record_run()`, or `ScheduleStore.save_schedule()`.
   - Prevents accidental state mutation during dry-run testing. Returns `DispatchResult(dispatched=False, reason="Dry run / simulation mode")`.

4. **Deduplication & Error Recovery**:
   - Active dispatch set `_active_dispatches: set[str]` with `try ... finally` guarantees no duplicate concurrent execution of the same schedule within a dispatch cycle.
   - If goal planning or execution raises an unhandled exception, `ScheduleDispatcher` records the goal failure in `GoalManager` and advances `sched.record_run()` to prevent infinite retry loops on broken tasks.

5. **Centralized Domain Events**:
   - `ScheduleTriggered`, `ScheduleRunRecorded`, and `ScheduleSkipped` are defined in `src/aura/events/models.py` and published over `EventBus`.

## Consequences
- **Positive**: 100% deterministic execution binding, full state persistence in SQLite, safe dry-run mode, thread-safe deduplication, complete event observability, 100% backward compatible with AURA 1.5.
- **Negative**: Continuous automatic background scheduling requires Stage 4 runtime loop runner.
