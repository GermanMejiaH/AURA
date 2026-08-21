# ADR-018 — Transactional Execution & Failure Compensation

* **Status:** ACCEPTED
* **Date:** 2026-08-19
* **Authors:** Architect Principal & Auditor Adversarial AURA 1.6
* **Deciders:** Core Engineering Team

---

## 1. Context & Problem Statement

In AURA 1.6, Stage 11 established high-level prioritization and policy evaluation (`RuntimePolicyEngine`), Stage 10 enforced runtime governance (`RuntimeGovernanceEngine`), Stage 3 dispatched trigger schedules (`ScheduleDispatcher`), and Stage 4 ran continuous autonomy loops (`ContinuousAutonomyRuntime`).

However, prior to Stage 12, action execution lacked formal transactional guarantees, state tracking (`PENDING`, `EXECUTING`, `COMMITTING`, etc.), explicit classification of failure types (`TRANSIENT`, `PERMANENT`, `VALIDATION`, `TIMEOUT`), retry policies with exponential backoff, idempotency protection against duplicate side effects, and structured reverse-order rollback (`C -> B -> A`) or compensation when multi-step or single-step operations fail.

Stage 12 addresses these gaps by implementing a thread-safe `RuntimeExecutionEngine` layer situated directly between Stage 3 dispatching and actual action execution.

---

## 2. Decision & Architectural Principles

We implement **Stage 12 — Transactional Execution, Action Reliability & Failure Compensation** as a non-breaking, incremental layer:

1. **Pipeline Ordering (Mandatory Scoping)**:
   The execution chain strictly follows:
   `Trigger / Schedule -> Policy (Stage 11) -> Governance (Stage 10) -> Dispatcher (Stage 3) -> RuntimeExecutionEngine (Stage 12) -> Action -> Commit / Rollback / Compensation -> Observability (Stage 7) + Persistence (Stage 9)`.
   `RuntimeExecutionEngine` NEVER bypasses Stage 11 Policy or Stage 10 Governance.

2. **Execution States (`ExecutionState`)**:
   Supported states: `PENDING`, `PREPARING`, `VALIDATING`, `EXECUTING`, `COMMITTING`, `COMMITTED`, `ROLLING_BACK`, `ROLLED_BACK`, `COMPENSATING`, `COMPENSATED`, `FAILED`, `CANCELLED`, `TIMED_OUT`.

3. **Failure Classification (`ExecutionFailureType`)**:
   `TRANSIENT`, `PERMANENT`, `VALIDATION`, `TIMEOUT`, `CANCELLED`, `ROLLBACK_FAILURE`, `COMPENSATION_FAILURE`, `UNKNOWN`.

4. **Retry Policy (`RetryPolicy`)**:
   Configurable `max_attempts` (default 3), `backoff_seconds`, and a set of `retryable_failures` (default `TRANSIENT`, `TIMEOUT`). Retries execute without `time.sleep` blocking during tests.

5. **Idempotency Protection**:
   `idempotency_key` deduplicates identical action requests. Terminal states (`COMMITTED`, `COMPENSATED`) return cached `ExecutionResult`s. Concurrent execution requests for the same idempotency key are protected by `threading.RLock`.

6. **Transaction Stack & Failure Compensation**:
   `ExecutionTransaction` registers executed actions. Upon failure, `rollback()` is executed in reverse order (`stepN -> ... -> step1`). If rollback fails or is insufficient, `compensate()` is executed in reverse order.

7. **EventBus Integration**:
   Emits 10 Stage 12 lifecycle events: `RuntimeExecutionStarted`, `RuntimeExecutionValidated`, `RuntimeExecutionCompleted`, `RuntimeExecutionFailed`, `RuntimeExecutionRetrying`, `RuntimeExecutionRolledBack`, `RuntimeExecutionCompensating`, `RuntimeExecutionCompensated`, `RuntimeExecutionCancelled`, `RuntimeExecutionTimedOut`.

---

## 3. Consequences

### Positive
* Deterministic, safe, transactional action execution with full rollback/compensation guarantees.
* Protection against duplicate side-effects via idempotency deduplication and thread-safe locking.
* Full compatibility with all previous stages (1–11).
* Complete observability through 10 new Stage 12 lifecycle events and control plane diagnostics (`get_execution_snapshot()`, `get_execution_history()`).

### Negative
* Slight CPU overhead for lock acquisition (`threading.RLock`) and memory consumption for history tracking (`autonomy.execution_history_size`).

---

## 4. Verification

* `tests/unit/test_aura_16_stage12_execution.py`: 28 unit test scenarios (100% pass).
* Full pytest suite: 935 unit tests passed.
* Static Analysis: `ruff check`, `ruff format`, `mypy src/aura` clean (0 warnings/errors).
