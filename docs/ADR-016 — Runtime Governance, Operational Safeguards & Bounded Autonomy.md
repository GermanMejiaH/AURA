# ADR-016 — Runtime Governance, Operational Safeguards & Bounded Autonomy

## Status
APPROVED AND FROZEN (Stage 10)

## Context
AURA 1.6 Stages 1–9 established temporal scheduling, deterministic evaluation, goal dispatch, execution loop, lifecycle bootstrap, health monitoring, self-recovery, operational diagnostics telemetry, Control Plane, and persistent state crash recovery.
However, continuous autonomous execution required operational safeguards, bounded autonomy limits, circuit breakers for failing actions, action rate limiting, and permission scope controls (`AutonomyScope`) to prevent runaway operations or unauthorized execution in constrained environments.

## Decision
We implement **Stage 10 — Runtime Governance, Operational Safeguards & Bounded Autonomy** via `RuntimeGovernanceEngine`:

1. **Operational Permission Scopes (`AutonomyScope`)**:
   - `UNRESTRICTED`: Full autonomous execution permitted.
   - `READ_ONLY`: Blocks mutating actions (`is_mutating=True`), permitting read-only inspection.
   - `SANDBOXED`: Restricts execution to non-external/non-destructive operations.
   - `DISABLED`: Suspends all autonomous execution regardless of runtime state.

2. **Circuit Breakers (`CircuitState`: `CLOSED`, `OPEN`, `HALF_OPEN`)**:
   - Tracks consecutive action failures (`record_action_outcome(success=False)`).
   - Trips to `OPEN` when failure count reaches `circuit_failure_threshold` (default: 5), blocking execution and emitting `CircuitBreakerTripped`.
   - Transitions to `HALF_OPEN` after `circuit_cooloff_seconds` (default: 60s) to safely test recovery.
   - Resets to `CLOSED` on successful action outcome (`CircuitBreakerReset`).

3. **Sliding-Window Rate Limiting**:
   - Enforces `rate_limit_max_calls_per_minute` across a 60-second sliding window to prevent action storms.

4. **Integration with `ScheduleDispatcher`, `RuntimeControlPlane`, and `AutonomyModule`**:
   - `ScheduleDispatcher` evaluates `evaluate_action()` before dispatching due schedules and records execution outcomes.
   - `RuntimeControlPlane` provides `set_governance_scope()` and `get_governance_snapshot()`.
   - Registered in `DependencyContainer` and resolved by `AutonomyModule`.

5. **EventBus Integration**:
   - `AutonomyScopeChanged`
   - `CircuitBreakerTripped`
   - `CircuitBreakerReset`
   - `GovernanceExecutionBlocked`

## Consequences
- **Bounded Autonomy**: Administrators can constrain runtime authority dynamically without stopping the execution loop.
- **Fail-Fast & Resource Protection**: Circuit breakers prevent repeated resource waste on broken targets.
- **Thread Safety**: All state mutators in `RuntimeGovernanceEngine` are synchronized with `threading.RLock()`.
- **100% Backward Compatibility**: Stages 1–9 operate without regression.
