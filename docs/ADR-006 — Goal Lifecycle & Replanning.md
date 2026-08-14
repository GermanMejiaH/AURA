# ADR-006 — Goal Lifecycle & Replanning Integration (AURA 1.5 Stage 5)

## Status
Accepted

## Context
AURA 1.5 Stage 4 introduced deterministic goal selection (`GoalSelector`) and deliberation integration (`AgentPlanner.plan_next_goal()`). To close the complete agentic goal cycle without introducing background threads, infinite loops, or unconstrained tool execution, AURA requires a deterministic link connecting plan execution outcomes back to `PersistentGoal` lifecycle management, event logging, memory consolidation, and re-prioritization.

## Decision
1. **Responsibility Separation**:
   - `AgentExecutor`: Executes tasks, runs `ActionVerifier` & `CognitiveReflector`, publishes `AgentPlanCompleted`. Does NOT touch SQLite or `GoalManager`.
   - `GoalManager`: Owns `PersistentGoal` lifecycle transitions (`record_execution_outcome()`), updates progress, and publishes domain events (`GoalOutcomeRecorded`).
   - `AgentPlanner`: Coordinates `execute_goal_cycle()`: `SELECT` -> `PLAN` -> `ACT` -> `VERIFY` -> `REFLECT` -> `LEARN` -> `UPDATE GOAL` -> `RE-PRIORITIZE`.

2. **Outcome Mapping & Progress Rules**:
   - **SUCCESS / COMPLETED**: All tasks succeeded -> `completion_percentage = 100.0`, status `COMPLETED`.
   - **PARTIAL_PROGRESS**: Sub-tasks succeeded -> `completion_percentage = (succeeded / total) * 100.0` (clamped `0.0` - `100.0`), status `ACTIVE`.
   - **FAILED**: Unrecoverable task failure -> status `FAILED`.
   - **BLOCKED**: Task waiting user confirmation / approval -> status `BLOCKED`.
   - **CANCELLED**: User or policy cancellation -> status `CANCELLED`.

3. **Idempotency & Terminal Invariants**:
   - Terminal goals (`COMPLETED`, `CANCELLED`) ignore subsequent outcome recordings to prevent accidental overwrites.
   - Progress percentage is strictly clamped within `[0.0, 100.0]`.

4. **Event Logging**:
   - `GoalOutcomeRecorded`: Published on outcome registration containing `goal_id`, `plan_id`, `status`, `completion_percentage`, `strategy_id`, `reason`.

## Consequences
- **Positive**: 100% deterministic, side-effect free, idempotent, safe against prompt injection or unconstrained tool execution, 100% backward compatible.
- **Negative**: Continuous execution across multiple goals requires explicit caller iteration over `execute_goal_cycle()`. Infinite background daemon loops remain deferred to Stage 6.
