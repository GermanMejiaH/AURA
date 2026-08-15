# AURA 1.5 Release Manifest

## 1. Release Identity
- **Version**: AURA 1.5 (Goal-Driven Agency, Persistent Goals & Long-Horizon Agency Baseline)
- **Purpose**: Introduce long-horizon persistent goal management, deterministic goal prioritization and selection, deliberation-driven planning, execution outcome recording, and goal lifecycle management without breaking AURA 1.4 backward compatibility.
- **Baseline Foundation**: AURA 1.4 (Strategic Deliberation & Strategy Selection Baseline - 520 tests passing)
- **Release / Hardening Commit**: `68a53f5 chore(aura): harden 1.5 release baseline`

## 2. Capabilities Delivered
- **Persistent Goals Domain Model**: `PersistentGoal`, `GoalStatus`, `GoalPriority`, `GoalProgress`, `GoalContextRef`, and `to_goal_model()` conversion.
- **SQLite Goal Persistence (`GoalStore`)**: Dedicated thread-safe persistence layer reusing `SQLiteMemoryStore` connection locking and foreign keys for table `persistent_goals`.
- **Domain Lifecycle Management (`GoalManager`)**: Domain service providing CRUD operations, status management, progress tracking, logical cancellation, physical deletion, and execution outcome recording (`record_execution_outcome()`).
- **Deterministic Goal Prioritization (`GoalPrioritizer`)**: Pure, side-effect free mathematical scoring engine ranking goals based on explicit priority, status, and remaining progress.
- **Cognitive Context Integration**: Passive injection of top-ranked `prioritized_goals` into `CognitiveContext` and `CognitiveContextBuilder` without direct SQLite coupling.
- **Deterministic Goal Selection (`GoalSelector`)**: Pure filtering engine choosing the top eligible goal (`PENDING` or `ACTIVE`) for deliberation and plan generation.
- **Goal-Driven Agent Planner Integration (`AgentPlanner`)**: Methods `plan_next_goal()` and `execute_goal_cycle()` linking persistent goal selection to E2E strategic deliberation and plan execution.
- **Execution Outcome Recording**: Synchronizing plan results back to `PersistentGoal` lifecycle status and progress percentage while respecting terminal status invariants.
- **Event Bus Integration**: Domain event notifications (`PersistentGoalCreated`, `GoalUpdated`, `GoalStatusChanged`, `GoalProgressUpdated`, `GoalSelectedForExecution`, `GoalOutcomeRecorded`).
- **Episodic Learning Integration**: Automatic episode consolidation via `EpisodicMemoryConsolidator` on `AgentPlanCompleted`.
- **E2E Agency Contract Test**: Dedicated contract test (`tests/integration/test_aura_15_agency_contract.py`) validating the full pipeline from goal persistence to re-selection.

## 3. Final Architecture

```text
GoalStore / SQLite
        ↓
GoalManager
        ↓
GoalPrioritizer
        ↓
GoalSelector
        ↓
AgentPlanner
        ↓
DeliberationEngine ──► OutcomeSimulator ──► StrategySelector
        ↓
AgentPlan
        ↓
AgentExecutor ──► ActionVerifier ──► CognitiveReflector ──► EpisodicMemoryConsolidator
        ↓
GoalManager.record_execution_outcome()
        ↓
Re-prioritize
        ↓
Next Goal
```

### Component Responsibilities
- **`GoalStore`**: Pure database persistence (SQL queries, schema initialization, JSON serialization, row mapping). No cognitive logic or event publishing.
- **`GoalManager`**: Domain lifecycle manager for `PersistentGoal` objects. Handles state transitions, progress tracking, execution outcome recording, and domain event publishing.
- **`GoalPrioritizer`**: Pure, side-effect free mathematical scoring engine. Scores, ranks, and provides explanations for `PersistentGoal` instances.
- **`GoalSelector`**: Pure, side-effect free eligibility filter. Selects the single highest-ranked eligible goal (`PENDING` or `ACTIVE`) for execution planning.
- **`AgentPlanner`**: Planning and deliberation orchestrator. Translates goals to plans (`deliberate_and_plan`), selects eligible persistent goals (`plan_next_goal`), and coordinates single-step goal execution cycles (`execute_goal_cycle`).
- **`DeliberationEngine`**: Generates strategy candidates (`StrategyCandidate`) for a given goal.
- **`OutcomeSimulator`**: Evaluates strategy candidates against historical episodic memory using `MemoryRetriever`.
- **`StrategySelector`**: Chooses the optimal `StrategySelection` using multi-criteria scoring and constraints validation.
- **`AgentPlan`**: Domain model encapsulating goal, tasks, assigned strategy ID/name, and execution state.
- **`AgentExecutor`**: Executes plan tasks safely. Runs `ActionVerifier` and `CognitiveReflector`, publishes `AgentPlanCompleted`. Does NOT access SQLite or `GoalStore`.
- **`ActionVerifier` & `CognitiveReflector`**: Post-execution verification and reflection analysis.
- **`EpisodicMemoryConsolidator`**: Subscribes to `AgentPlanCompleted` and records episode details in episodic memory.

## 4. Architectural Boundaries

| Activity / Concern | Authorized Component | Explicitly Forbidden Components |
|---|---|---|
| Direct SQLite Access for Goals | `GoalStore` | `AgentExecutor`, `GoalPrioritizer`, `GoalSelector`, `CognitiveContextBuilder` |
| PersistentGoal Mutation | `GoalManager`, `PersistentGoal` | `GoalSelector`, `GoalPrioritizer`, `AgentExecutor`, LLM Providers |
| Goal Selection for Execution | `GoalSelector` | `AgentExecutor`, `GoalStore`, LLM Providers |
| Goal Prioritization / Scoring | `GoalPrioritizer` | `AgentExecutor`, `GoalStore`, LLM Providers |
| Tool Action Execution | `AgentExecutor` | `GoalSelector`, `GoalPrioritizer`, `GoalManager`, `AgentPlanner` |
| LLM Inference Calls | LLM Providers (via `CognitionModule`) | `GoalPrioritizer`, `GoalSelector`, `GoalStore`, `GoalManager` |
| Goal Lifecycle Event Emission | `GoalManager`, `AgentPlanner` | `GoalStore`, `AgentExecutor` (direct goal events) |
| Episodic Memory Consolidation | `EpisodicMemoryConsolidator` | `GoalStore`, `GoalSelector` |

## 5. Goal State Machine

The `GoalStatus` enum defines 7 states:

```text
PENDING
   │
   ├──► ACTIVE ──► COMPLETED (Terminal)
   │      │
   │      ├──► FAILED
   │      ├──► BLOCKED
   │      └──► CANCELLED (Terminal)
   │
   ├──► PAUSED ──► ACTIVE
   │
   └──► CANCELLED (Terminal)
```

### Valid State Transitions
- **`PENDING` $\to$ `ACTIVE`**: Triggered when a goal is selected for execution or progress is recorded.
- **`PENDING` $\to$ `CANCELLED`**: Triggered by explicit logical cancellation (`cancel_goal`).
- **`ACTIVE` $\to$ `COMPLETED`**: Triggered when all plan tasks succeed or progress reaches 100%.
- **`ACTIVE` $\to$ `FAILED`**: Triggered when plan execution encounters an unrecoverable failure.
- **`ACTIVE` $\to$ `BLOCKED`**: Triggered when plan execution requires user confirmation (`WAITING_CONFIRMATION`).
- **`ACTIVE` $\to$ `PAUSED`**: Triggered by explicit user/operator pause.
- **`ACTIVE` $\to$ `CANCELLED`**: Triggered by explicit logical cancellation.
- **`BLOCKED` $\to$ `ACTIVE`**: Triggered when blocked task is authorized or unblocked.
- **`PAUSED` $\to$ `ACTIVE`**: Triggered when paused goal is resumed.
- **`COMPLETED` & `CANCELLED`**: Immutable terminal states. `record_execution_outcome()` ignores subsequent outcome recordings on terminal goals to ensure idempotency.

## 6. Event Catalog

| Event Class | Producer | Emission Trigger | Key Payload Fields | Purpose |
|---|---|---|---|---|
| `PersistentGoalCreated` | `GoalManager` | `create_goal()` | `goal_id`, `description`, `priority`, `status` | Notify creation of a new persistent goal |
| `GoalUpdated` | `GoalManager` | `update_goal()` | `goal_id`, `updated_fields` | Notify modification of goal attributes |
| `GoalStatusChanged` | `GoalManager` | `set_status()` | `goal_id`, `old_status`, `new_status` | Notify lifecycle status state transition |
| `GoalProgressUpdated` | `GoalManager` | `update_progress()` | `goal_id`, `completion_percentage`, `milestone_added` | Notify progress percentage or milestone updates |
| `GoalSelectedForExecution` | `AgentPlanner` | `plan_next_goal()` | `goal_id`, `description`, `score`, `rank`, `selection_reason` | Audit goal selection for execution planning |
| `StrategyDeliberated` | `AgentPlanner` | `deliberate_and_plan()` | `goal_id`, `candidates_count` | Audit strategy candidate generation |
| `StrategySelected` | `AgentPlanner` | `deliberate_and_plan()` | `goal_id`, `strategy_id`, `strategy_name` | Audit chosen strategic candidate |
| `AgentPlanCompleted` | `AgentExecutor` | `execute_plan()` | `plan_id`, `completed`, `failed`, `verification`, `reflection`, `strategy_id` | Audit plan completion and trigger episodic consolidation |
| `GoalOutcomeRecorded` | `GoalManager` | `record_execution_outcome()` | `goal_id`, `plan_id`, `status`, `completion_percentage`, `strategy_id`, `reason` | Audit goal lifecycle outcome after plan run |

## 7. Persistence Contract
- **Table Name**: `persistent_goals`
- **Columns**:
  - `goal_id TEXT PRIMARY KEY`
  - `description TEXT NOT NULL`
  - `priority TEXT NOT NULL`
  - `status TEXT NOT NULL`
  - `created_at TEXT NOT NULL`
  - `updated_at TEXT NOT NULL`
  - `success_criteria_json TEXT NOT NULL DEFAULT '[]'`
  - `constraints_json TEXT NOT NULL DEFAULT '[]'`
  - `context_json TEXT NOT NULL DEFAULT '{}'`
  - `progress_json TEXT NOT NULL DEFAULT '{}'`
  - `parent_goal_id TEXT`
  - `risk_tolerance TEXT NOT NULL DEFAULT 'MEDIUM'`
  - `FOREIGN KEY (parent_goal_id) REFERENCES persistent_goals(goal_id) ON DELETE SET NULL`
- **Indexes**:
  - `idx_persistent_goals_status ON persistent_goals(status)`
  - `idx_persistent_goals_priority ON persistent_goals(priority)`
  - `idx_persistent_goals_parent ON persistent_goals(parent_goal_id)`
- **JSON Serialization**: Structured fields (`success_criteria`, `constraints`, `context`, `progress`) are stored via `json.dumps()` and parsed via `json.loads()`.
- **Corrupt Data Handling**: Exception blocks in `_row_to_persistent_goal()` catch JSON parse failures or invalid enum values and fall back safely to empty collections or default enums (`GoalPriority.MEDIUM`, `GoalStatus.PENDING`, `RiskLevel.MEDIUM`).
- **Thread Safety**: Uses `threading.RLock` inherited from `SQLiteMemoryStore`. All SQLite transactions execute within `with self._lock:` blocks.
- **Deletion Policy**: Logical cancellation (`cancel_goal()`) updates status to `CANCELLED` to preserve cognitive history. Physical deletion (`delete_goal()`) executes `DELETE FROM persistent_goals WHERE goal_id = ?`.

## 8. Determinism Contract
- **Goal Prioritization (`GoalPrioritizer`)**: Pure mathematical scoring formula:
  $$\text{score} = W_{\text{priority}} + W_{\text{status}} + W_{\text{progress}}$$
  - $W_{\text{priority}}$: `CRITICAL` = 40.0, `HIGH` = 30.0, `MEDIUM` = 20.0, `LOW` = 10.0.
  - $W_{\text{status}}$: `ACTIVE` = +15.0, `PENDING` = +10.0, `BLOCKED` = +5.0, `PAUSED` = +0.0, `COMPLETED` = -50.0, `FAILED` = -50.0, `CANCELLED` = -100.0.
  - $W_{\text{progress}}$: $(100.0 - \text{completion\_percentage}) \times 0.1$ for non-terminal goals; 0.0 for terminal goals.
  - **Tie-Breaking Rule**: Sorts strictly by `(-score, created_at ASC, goal_id ASC)`.
- **Goal Selection (`GoalSelector`)**: Pure eligibility filter:
  - Ineligible statuses: `INELIGIBLE_STATUSES = {COMPLETED, FAILED, CANCELLED, PAUSED, BLOCKED}`.
  - Eligible statuses: `PENDING`, `ACTIVE`.
  - Picks the first eligible goal from `PrioritizedGoal[]` list. Returns `None` cleanly if no goal is eligible.

## 9. Agency Cycle Contract

```text
SELECT   (GoalSelector picks highest ranked eligible PersistentGoal)
PLAN     (AgentPlanner runs DeliberationEngine, OutcomeSimulator, StrategySelector -> AgentPlan)
ACT      (AgentExecutor runs plan tasks safely)
VERIFY   (ActionVerifier evaluates tool execution output)
REFLECT  (CognitiveReflector synthesizes lesson learned and root cause)
LEARN    (EpisodicMemoryConsolidator saves episode details on AgentPlanCompleted)
UPDATE   (GoalManager.record_execution_outcome updates PersistentGoal progress/status in SQLite)
RE-PRIORITIZE (GoalPrioritizer ranks updated goals for next selection)
```

## 10. Safety Boundaries (Non-Features of AURA 1.5)
- **No Background Daemon Threads**: Goal execution cycles do NOT run in infinite background thread loops.
- **No Autonomous Scheduling**: No cron, interval, or temporal scheduling engines exist in AURA 1.5.
- **No Continuous Autonomous Loops**: Each `execute_goal_cycle()` run executes exactly one goal cycle synchronously when called.
- **No Implicit Tool Authorization**: `GoalSelector` chooses goals for planning; it does NOT grant automatic permission for tool execution. Safety constraints in `AgentExecutor` remain strictly enforced.
- **No Direct SQLite Access in Executor**: `AgentExecutor` remains completely isolated from database persistence.

## 11. Test & Quality Baseline
- **Total Tests**: `664 passed in 19.46s`
- **Ruff Code Formatting & Lints**: `All checks passed!` (0 errors)
- **MyPy Static Type Checker**: `Success: no issues found in 120 source files` (0 errors)
- **Git Diff Check**: Clean (`git diff --check` passed with 0 errors)
- **Git Status**: Clean working tree
- **End-to-End Contract Integration Test**: `tests/integration/test_aura_15_agency_contract.py`

## 12. Known Limitations
- **Manual Cycle Triggering**: Executing multiple goals sequentially requires explicit caller iteration over `AgentPlanner.execute_goal_cycle()`. Continuous autonomous scheduling is intentionally reserved for AURA 1.6.
- **Explicit Unblocking Requirement**: `BLOCKED` goals remain ineligible for selection until their status is explicitly updated via `GoalManager`.

## 13. Release Baseline
- **Release / Hardening Commit**: `68a53f5`
- **Release Freeze Commit**: `docs(aura): freeze 1.5 release baseline`
- **Release Date**: August 14, 2026
- **Working Tree State**: Clean (`nothing to commit, working tree clean`)
- **Recommended Validation Command**: `.\.venv\Scripts\pytest`
