# ADR-020: Adaptive Policy, Human-in-the-Loop Decision & Controlled Runtime Adaptation

## Status
APPROVED AND FROZEN (AURA 1.6 — STAGE 14)

## Context
Stage 13 introduces `RuntimeExperienceEngine` and `RuntimeExperienceStore` to transform execution outcomes into operational experience and decision recommendations. However, Stage 13 recommendations are purely advisory and cannot modify system behavior directly.

Stage 14 establishes `RuntimeAdaptivePolicyEngine`, `RuntimeAdaptationStore`, and `RuntimeAdaptationValidator` to translate Stage 13 experience recommendations into controlled, validated, bounded, human-in-the-loop operational adaptation proposals.

## Architecture & Conceptual Pipeline
```
Stage 13 Experience
      ↓
Stage 14 Adaptive Policy Engine
      ↓
Adaptation Proposal
      ↓
Runtime Adaptation Validator (Safety Bounds & Constraint Verification)
      ↓
Operator Approval (Human-in-the-Loop Decision)
      ↓
Controlled Application
      ↓
Stage 11 Policy Engine (Priority & Conflict Resolution)
      ↓
Stage 10 Governance Engine (Inviolable Safeguards & Scope Check)
      ↓
Stage 12 Execution Engine (Transactional Execution)
```

## Fundamental Safety Rules
1. **Never Direct Execution**: Stage 13 Experience cannot bypass Stage 14 or directly mutate Stage 10 Governance or Stage 11 Policy.
2. **Decoupled Approval & Application**: `approve_adaptation()` sets proposal status to `APPROVED` but DOES NOT apply the change. `apply_adaptation()` must be invoked separately.
3. **Inviolable Governance & Scope**: Proposals that attempt to modify Stage 10 `GovernancePolicy`, escalate `AutonomyScope` to `UNRESTRICTED`, delete `CircuitBreakers`, or bypass Stage 11 Policy Engine are IMMEDIATELY `BLOCKED` with `RuntimeAdaptationBlocked`.
4. **Idempotency & Reversibility**: `apply_adaptation()` and `rollback_adaptation()` are fully idempotent and auditable.
5. **Human-in-the-Loop Default**: By default (`autonomy.adaptation_require_operator_approval = True`), all proposals require explicit operator decision. Auto-apply is disabled by default (`autonomy.adaptation_auto_apply_enabled = False`).

## Data Models & Enums
- **`AdaptationAction`**: `PROPOSE`, `APPROVE`, `REJECT`, `APPLY`, `ROLLBACK`, `EXPIRE`, `BLOCK`.
- **`AdaptationStatus`**: `PROPOSED`, `PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `VALIDATED`, `APPLIED`, `ROLLED_BACK`, `EXPIRED`, `BLOCKED`.
- **`AdaptationType`**: `REDUCE_FREQUENCY`, `INCREASE_FREQUENCY`, `CHANGE_PRIORITY`, `CHANGE_RETRY_POLICY`, `CHANGE_OBSERVATION_LEVEL`, `REQUIRE_OPERATOR_REVIEW`, `DISABLE_ACTION`, `ENABLE_ACTION`, `CHANGE_RESOURCE_LIMIT`, `NO_CHANGE`.
- **`AdaptationProposal`**: Frozen dataclass representing a proposed adaptation.
- **`AdaptationPolicy`**: Hard limits on allowed operational adjustments.
- **`OperatorDecision`**: Audit log record for operator approve/reject decisions.
- **`AdaptationStatusSnapshot`**: Immutable snapshot of adaptation telemetry.

## Persistence
SQLite table `runtime_adaptation_proposals` and `runtime_operator_decisions` stored via `SQLiteMemoryStore` with full thread safety (`threading.RLock`).

## Audit & Verification
Verified with 40/40 dedicated Stage 14 unit and integration test cases and 1010/1010 full test suite pass.
