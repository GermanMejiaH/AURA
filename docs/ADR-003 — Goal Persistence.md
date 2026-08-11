# ADR-003 — Goal Persistence Architecture (AURA 1.5 Stage 2)

## Status
Accepted

## Context
AURA 1.5 introduces `PersistentGoal` objects that maintain cognitive state and progress over long horizons across sessions and system restarts.
A persistence backend is required to securely store, retrieve, filter, and update persistent goals without duplicating database connections, introducing data corruption, or breaking existing memory stores.

## Decision
1. **Infrastructure Reuse**:
   - Reuse the existing thread-safe `SQLiteMemoryStore` engine (`sqlite3`, `RLock`, `PRAGMA foreign_keys = ON;`, `data/aura.db`) rather than initializing a separate database connection or file.
   - Create a dedicated `GoalStore` abstraction in `src/aura/cognition/goals/store.py` responsible exclusively for CRUD SQL operations on the `persistent_goals` table.

2. **Database Schema**:
   - Create the `persistent_goals` table with foreign key references for hierarchical parent goals (`parent_goal_id`).
   - Store complex nested structures (`success_criteria`, `constraints`, `context`, `progress`) as deterministic JSON strings (`json.dumps`, `json.loads`).
   - Create indexes on `status`, `priority`, and `parent_goal_id` for efficient filtering.

3. **Application & Domain Layering**:
   - `GoalManager` in `src/aura/cognition/goals/manager.py` acts as the domain orchestration layer over `GoalStore`.
   - `GoalManager` handles goal validation, state transition logic, progress updates, logical vs. physical deletion decisions, and event publishing (`EventBus`).
   - `GoalStore` handles pure database persistence without cognitive or event publishing logic.
   - `PersistentGoal` domain model remains clean of database/SQL logic.

4. **Deletion Policy**:
   - `cancel_goal(goal_id)` performs a logical status update (`GoalStatus.CANCELLED`) to preserve cognitive history and learning context.
   - `delete_goal(goal_id)` provides physical removal when explicitly requested.

5. **Event Integration**:
   - `GoalManager` publishes typed events (`PersistentGoalCreated`, `GoalUpdated`, `GoalStatusChanged`, `GoalProgressUpdated`) via AURA's `EventBus` when state changes occur.

## Consequences
- **Positive**: Zero code duplication for connection management, clean separation of concerns, 100% thread safety, full backward compatibility with AURA 1.4 deliberation.
- **Negative**: Requires maintenance of schema migration hooks in SQLite initialization if schema evolves in future releases.
