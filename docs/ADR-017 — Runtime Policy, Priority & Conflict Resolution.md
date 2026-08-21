# ADR-017 — Runtime Policy, Intent Prioritization & Conflict Resolution

- **Status**: Approved & Frozen
- **Date**: 2026-08-18
- **Context**: AURA 1.6 Stage 11 — Runtime Policy, Intent Prioritization & Conflict Resolution
- **Deciders**: AURA Core Architecture Team

---

## 1. Context & Problem Statement

After establishing temporal scheduling (Stage 1-3), continuous autonomy runtime (Stage 4-5), health monitoring and self-recovery (Stage 6), operational observability (Stage 7), control plane management (Stage 8), state persistence & recovery (Stage 9), and runtime governance & bounded autonomy (Stage 10), AURA needed a deterministic operational layer to prioritize tasks, resolve resource conflicts, enforce deadlines, deduplicate executions, and manage priority aging.

Without a dedicated policy and priority resolution engine:
1. Low-priority tasks could block high-priority tasks during shared resource contention.
2. Identical operational schedules could trigger duplicate concurrent executions.
3. Expired tasks past their execution deadline could run silently without auditability.
4. Long-waiting low-priority tasks could suffer from indefinite starvation without deterministic priority aging.

---

## 2. Decision & Architectural Overview

We introduced `RuntimePolicyEngine` in `src/aura/cognition/scheduling/resolution.py`, providing a thread-safe, deterministic policy, priority resolution, and conflict management engine for AURA 1.6.

### Pipeline Execution Order
Operational evaluation follows a strict unidirectionally scoped execution chain:

```
    TemporalSchedule / Trigger
                │
                ▼
    [ Stage 11: RuntimePolicyEngine ]  ──(Defer / Cancel / Block)──► Skip & Emit Policy Event
                │
            (ALLOW)
                ▼
    [ Stage 10: RuntimeGovernanceEngine ] ──(Scope / Circuit / Limit)──► Skip & Emit Governance Event
                │
            (ALLOW)
                ▼
    [ Stage 3: ScheduleDispatcher ]
                │
                ▼
    [ Stage 4: ContinuousAutonomyRuntime Execution ]
                │
                ▼
    [ Stage 7 / Stage 9 Observability & Persistence ]
```

**CRITICAL RULE**: A `PolicyAction.ALLOW` decision CANNOT bypass Stage 10 `RuntimeGovernanceEngine` safeguards (`AutonomyScope`, `CircuitBreaker`, or `RateLimiting`). If Governance blocks an action, the final dispatch result remains `dispatched=False` (`Governance blocked execution`).

---

## 3. Domain Models & Abstractions

1. **`PolicyPriority` (Enum)**:
   - `CRITICAL` (weight = 100.0)
   - `HIGH` (weight = 75.0)
   - `NORMAL` (weight = 50.0)
   - `LOW` (weight = 25.0)
   - `BACKGROUND` (weight = 10.0)

2. **`PolicyAction` (Enum)**:
   - `ALLOW`: Authorized to proceed to Governance evaluation.
   - `DEFER`: Deferred due to higher priority resource contention or waiting window.
   - `CANCEL`: Cancelled due to expired deadline or duplicate execution key.
   - `REPLACE`: Replaced by higher priority pre-emption.
   - `BLOCK`: Blocked by operational policy rule.

3. **`ConflictType` (Enum)**:
   - `RESOURCE_CONFLICT`: Shared resource lock contention.
   - `MUTUAL_EXCLUSION`: Mutually exclusive operation.
   - `HIGHER_PRIORITY`: Higher priority task active.
   - `DEADLINE_EXPIRED`: Execution deadline timestamp passed.
   - `DUPLICATE`: Identical operational key currently active.
   - `GOVERNANCE_CONFLICT`: Conflict with active governance scope.

4. **`PolicyConflict` (Dataclass, frozen=True)**:
   - Immutable audit record detailing the conflict, winning task ID, losing task ID, resource ID, and timestamp.

5. **`RuntimePolicyDecision` / `PolicyDecision` (Dataclass, frozen=True)**:
   - Immutable decision outcome detailing `allowed`, `action`, `reason`, `effective_priority`, `base_priority`, `conflict`, and `timestamp`.

6. **`PolicyStatusSnapshot` (Dataclass, frozen=True)**:
   - Immutable diagnostics snapshot detailing evaluation counts (`total`, `allowed`, `deferred`, `cancelled`, `blocked`), conflicts detected, expired deadlines, active resource locks, and waiting tasks count.

---

## 4. Operational Mechanics

### A. Deterministic Priority Aging
- Boosts effective priority over waiting time using `Clock`/`TestClock`:
  `effective_priority = base_weight + min(max_aging_boost, elapsed_minutes * aging_rate)`
- Prevents starvation of low-priority tasks waiting over extended durations.
- Publishes `RuntimeTaskPriorityChanged` when priority boost thresholds are crossed.

### B. Deadline Enforcement
- Evaluates `deadline_at` or `deadline_iso` ISO timestamps against `clock.now_iso()`.
- If current time exceeds deadline, cancels execution (`PolicyAction.CANCEL`) with `ConflictType.DEADLINE_EXPIRED` and emits `RuntimeTaskCancelled`.

### C. Resource Contention & Locking
- Tracks `_resource_locks` (resource_id -> task_id).
- Tasks requiring busy resources are deferred (`PolicyAction.DEFER`) if held by tasks of equal/higher effective priority.
- Tasks with higher effective priority pre-empt locks held by lower priority tasks.
- `record_task_completion()` cleanly releases held locks upon completion.

### D. Deduplication
- Identifies active executions via `dedup_key` or `goal_id`.
- Cancels concurrent duplicate attempts (`PolicyAction.CANCEL`) with `ConflictType.DUPLICATE`.

---

## 5. System Integration

1. **`ScheduleDispatcher`**:
   - Evaluates `policy_engine.evaluate_schedule(sched, goal)` BEFORE Governance evaluation.
   - Calls `policy_engine.record_task_completion()` in `finally` block post-execution.
2. **`RuntimeControlPlane`**:
   - Exposes `get_policy_snapshot() -> PolicyStatusSnapshot | None`.
3. **`AutonomyModule`**:
   - Resolves/instantiates `RuntimePolicyEngine` during `on_initialize()`.
   - Registers `RuntimePolicyEngine` in `DependencyContainer`.
   - Wires `RuntimePolicyEngine` into `ScheduleDispatcher` and `RuntimeControlPlane`.
   - Exposes `get_policy_snapshot()`.
4. **`ConfigurationManager`**:
   - Registers default policy configuration options (`autonomy.policy_resolution_enabled`, `autonomy.priority_aging_enabled`, etc.).

---

## 6. Consequences & Compatibility

- **Thread Safety**: All state mutations in `RuntimePolicyEngine` are protected by `threading.RLock()`.
- **Zero Thread Leaks**: Uses existing clock abstractions without spawning background worker threads.
- **Stage 1–10 Compatibility**: Fully backward-compatible; all 887 existing tests pass cleanly without regression.
