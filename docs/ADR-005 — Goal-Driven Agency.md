# ADR-005 — Goal-Driven Agency & Deterministic Goal Selection (AURA 1.5 Stage 4)

## Status
Accepted

## Context
AURA 1.5 introduces autonomous goal-driven deliberation (`Goal-Driven Agency`). To decide which persistent goal to address without unrestricted execution or non-deterministic behavior, AURA requires an explicit selection stage (`GoalSelector`) that consumes prioritized goals (`PrioritizedGoal[]`), evaluates eligibility rules, and converts the top-ranked eligible goal into a `GoalModel` for deliberation and plan generation.

## Decision
1. **Separation of Responsibilities**:
   - `GoalStore`: Pure SQLite persistence.
   - `GoalManager`: Domain lifecycle management.
   - `GoalPrioritizer`: Pure deterministic goal ranking.
   - `GoalSelector`: Pure deterministic goal selection (`SelectedGoal | None`).
   - `DeliberationEngine`: Strategy candidate generation.
   - `OutcomeSimulator`: Strategic consequence evaluation.
   - `StrategySelector`: Best strategy choice.
   - `AgentPlanner.plan_next_goal()`: End-to-end orchestration up to `AgentPlan` creation without executing tool actions.

2. **Eligibility Rules (`GoalSelector`)**:
   - Ineligible statuses: `COMPLETED`, `FAILED`, `CANCELLED`, `PAUSED`, `BLOCKED`.
   - Eligible statuses: `PENDING`, `ACTIVE`.
   - Returns `SelectedGoal` with `goal`, `score`, `rank`, and `selection_reason`.
   - Returns `None` cleanly if no goals are eligible (no exception raised).

3. **Event Publishing**:
   - Emits `GoalSelectedForExecution(source="AgentPlanner", goal_id=..., description=..., score=..., rank=..., selection_reason=...)` on successful goal selection.

4. **Action Authorization Boundary**:
   - Goal selection chooses *which* goal to deliberate on; it does *not* grant automatic permission to execute tool actions. Execution remains bound by safety constraints in `AgentExecutor`.

## Consequences
- **Positive**: 100% deterministic, side-effect free, fully auditable, non-breaking to existing AURA 1.3/1.4 workflows, safe against unconstrained tool execution.
- **Negative**: Unblocking of `BLOCKED` goals currently requires explicit state transitions via `GoalManager` before `GoalSelector` considers them eligible.
