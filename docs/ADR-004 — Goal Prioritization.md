# ADR-004 — Deterministic Goal Prioritization & Contextual Integration (AURA 1.5 Stage 3)

## Status
Accepted

## Context
AURA 1.5 manages long-horizon `PersistentGoal` domain models. To deliberate and plan actions effectively, AURA requires a deterministic mechanism to evaluate, rank, and explain the relative importance of active persistent goals.
Furthermore, the top-ranked persistent goals must be injected into `CognitiveContext` as passive, sanitized context without introducing direct dependencies on SQLite or non-deterministic components (such as LLMs, vector search, or system clock randomness).

## Decision
1. **`PrioritizedGoal` Domain Struct**:
   - Represents a scored and ranked goal: `goal: PersistentGoal`, `score: float`, `rank: int`, `explanation: str`.
   - Provides a human-readable, deterministic explanation of why the goal received its rank.

2. **Deterministic Scoring Engine (`GoalPrioritizer`)**:
   - `GoalPrioritizer.prioritize(goals: list[PersistentGoal]) -> list[PrioritizedGoal]`
   - Pure, side-effect free computation based strictly on `PersistentGoal` attributes.
   - **Scoring Formula**:
     $$\text{score} = W_{\text{priority}} + W_{\text{status}} + W_{\text{progress}}$$
     - **Explicit Priority Weight ($W_{\text{priority}}$)**:
       `CRITICAL` = 40.0, `HIGH` = 30.0, `MEDIUM` = 20.0, `LOW` = 10.0.
     - **Status Weight ($W_{\text{status}}$)**:
       `ACTIVE` = +15.0, `PENDING` = +10.0, `BLOCKED` = +5.0, `PAUSED` = +0.0,
       `COMPLETED` = -50.0, `FAILED` = -50.0, `CANCELLED` = -100.0.
     - **Progress Weight ($W_{\text{progress}}$)**:
       $(100.0 - \text{completion\_percentage}) \times 0.1$ (for non-terminal goals).
   - **Tie-Breaking**: Sorts strictly by `score DESC`, then `created_at ASC`, then `goal_id ASC`.

3. **Cognitive Context Integration**:
   - `CognitiveContext` accepts an optional `prioritized_goals: list[PrioritizedGoal]` parameter.
   - `to_system_prompt()` appends a passive, sanitized section `[OBJETIVOS PERSISTENTES PRIORIZADOS]` to inform LLM reasoning.
   - `CognitiveContextBuilder` pulls `GoalManager` from `DependencyContainer` (if available) and passes the top-ranked goals to `CognitiveContext`, ensuring zero direct queries to SQLite.

## Consequences
- **Positive**: 100% deterministic, zero LLM overhead, side-effect free, fully explainable, safe against prompt injection, zero breaking changes to existing AURA 1.4/1.3 context or planning workflows.
- **Negative**: Dynamic context factors (such as temporal deadlines or location proximity) require explicit model fields in future releases before `GoalPrioritizer` can incorporate them.
