# ADR-021: Runtime Assurance, Observability, Audit & Recovery

## Status
APPROVED AND FROZEN (Stage 15 Complete)

## Context
Stage 15 introduces `RuntimeAssuranceEngine`, a transversal monitoring, invariant checking, audit trail, correlation, checkpointing, and safe recovery layer across Stages 1–14.

Stage 15 does NOT act as an autonomous execution engine or decision support mechanism. It strictly observes, verifies, audits, and coordinates safe system recovery and quarantine (SAFE_MODE) without bypassing Stage 10 Governance, Stage 11 Policy, Stage 12 Execution, Stage 13 Experience, or Stage 14 Adaptive Policy.

## Architecture & Principles
1. **Transversal Observability**: Continuously monitors component health (`HEALTHY`, `DEGRADED`, `RECOVERING`, `RECOVERED`, `FAILED`, `SAFE_MODE`).
2. **Runtime Invariants**: Evaluates critical and operational system invariants (`RuntimeInvariant`, `InvariantViolation`). Violations of `CRITICAL` severity automatically trigger `SAFE_MODE`.
3. **Immutable Audit Trail**: Records structured audit events (`AuditRecord`) in SQLite (`runtime_audit_records`) with cross-stage `correlation_id` tracking.
4. **Checkpointing & Recovery**: Creates point-in-time operational snapshots (`RuntimeCheckpoint`) and provides safe recovery workflows (`RecoveryResult`).
5. **Fail-Closed & SAFE_MODE**: Under uncertainty or critical invariant failure, system transitions to `SAFE_MODE`. Exiting `SAFE_MODE` requires explicit verification that no unresolved critical invariant violations exist.
6. **Non-Invasive Safety**: Checkpoints and automated recoveries NEVER lower Stage 10 Governance policies or elevate `AutonomyScope`.

## Verification
- Test coverage: 48/48 unit tests passing in `tests/unit/test_aura_16_stage15_assurance.py` (including ASSURE-01 to ASSURE-08).
- Repository suite: 1058/1058 tests passing cleanly.
- Static analysis & linting: MyPy and Ruff CLEAN.
