# ADR-019: Runtime Experience, Outcome Memory & Adaptive Decision Support

* **Status:** Accepted
* **Context:** AURA 1.6 Stage 13 — Runtime Experience, Outcome Memory & Adaptive Decision Support
* **Date:** 2026-08-19

## Context and Problem Statement
Prior to Stage 13, AURA 1.6 included transactional execution, failure handling, and compensation (Stage 12), deterministic runtime policy resolution (Stage 11), multi-level governance enforcement (Stage 10), and persistence (Stage 9). However, operational execution outcomes were not recorded or analyzed across executions. Without an operational outcome memory, the runtime had no mechanism to aggregate historical performance, compute action reliability metrics, detect recurring failure patterns, or advise operators on policy optimizations.

Stage 13 introduces a dedicated Operational Outcome Memory and Decision Support engine to record, analyze, and query execution history without compromising the strict authority of Stage 10 Governance or Stage 11 Policy.

## Decision Drivers
1. **Explainable & Deterministic Recommendations:** Avoid opaque ML models or statistical black boxes. All pattern detection rules and recommendation heuristics must be 100% deterministic and auditable.
2. **Support & Recommendation Only:** Decision support recommendations are strictly advisory (`SUPPORT/RECOMMENDATION`). Stage 13 CANNOT execute actions directly, modify `AutonomyScope`, bypass Stage 10 Governance, or alter Stage 11 Policy rules automatically.
3. **Decoupled Architecture & Event-Driven Observability:** Stage 13 subscribes exclusively to Stage 12 execution events (`RuntimeExecutionCompleted`, `RuntimeExecutionFailed`, etc.) to prevent infinite event loops.
4. **Thread-Safe & Idempotent Persistence:** Outcome records are stored atomically in a dedicated SQLite table (`runtime_outcome_history`), leveraging `SQLiteMemoryStore` infrastructure.
5. **Zero Breaking Changes:** Preserve all existing contracts and behavior across Stages 1–12.

## Considered Options
1. **Option 1: Direct Integration in Stage 12 Execution Engine.**
   - *Pros:* Immediate access to execution context.
   - *Cons:* Tight coupling; violates single responsibility principle; complicates Stage 12 transactional rollback logic.
2. **Option 2: Standalone Event-Driven Experience Layer (`RuntimeExperienceStore` + `RuntimeExperienceEngine`).**
   - *Pros:* Fully decoupled; thread-safe; subscribes via `EventBus`; exposes clean control plane query methods; preserves strict governance boundary.
   - *Cons:* Requires event synchronization and structured outcome models.

## Decision Outcome
**Chosen Option: Option 2 (Standalone Event-Driven Experience Layer).**

### Key Components:
- **`OutcomeType` & Domain Dataclasses:** `OutcomeType` (`SUCCESS`, `FAILURE`, `PARTIAL_SUCCESS`, `CANCELLED`, `TIMED_OUT`, `ROLLED_BACK`, `COMPENSATED`, `BLOCKED`, `DEFERRED`), `ExperienceConfidence`, `RecommendationType`, `OutcomeRecord`, `ActionExperience`, `ExperienceRecommendation`, `ExperienceStatusSnapshot`.
- **`RuntimeExperienceStore`:** Thread-safe SQLite store backing `runtime_outcome_history`. Provides methods `record_outcome`, `get_outcome`, `get_action_experience`, `get_recent_outcomes`, `get_failures`, `get_successes`, `clear_history`, and `count`.
- **`RuntimeExperienceEngine`:** Thread-safe engine (`threading.RLock`) managing outcome processing, pattern detection (`CONSECUTIVE_FAILURES`, `REPEATED_FAILURE_TYPE`, `TIMEOUT_PATTERN`, `ROLLBACK_PATTERN`, `COMPENSATION_PATTERN`, `DEGRADATION_PATTERN`), recommendation generation, and event publishing (`RuntimeOutcomeRecorded`, `RuntimeExperienceUpdated`, `RuntimeRecommendationGenerated`, `RuntimeFailurePatternDetected`, `RuntimeOperatorReviewRecommended`).
- **Control Plane & Autonomy Module Integration:** Exposes experience queries (`get_experience_snapshot()`, `get_action_experience()`, `get_recent_outcomes()`, `get_recommendations()`, `get_failure_patterns()`) in `RuntimeControlPlane` and `AutonomyModule`.
- **IoC Container Registration:** Registers `RuntimeExperienceStore` and `RuntimeExperienceEngine` in `DependencyContainer`.

## Compliance & Security Guarantees
- **Governance Supremacy:** Stage 10 Governance remains the ultimate execution barrier. Stage 13 recommendations do not mutate `AutonomyScope` or bypass circuit breakers.
- **Policy Determinism:** Stage 11 Policy Engine evaluates priority and resource conflicts independently of Stage 13 advisory signals.
- **Thread & Memory Safety:** All operations use reentrant locks (`RLock`) and parameterized SQL queries to prevent race conditions and SQL injection.

## Verification
- **Unit Tests:** 35 dedicated tests in `tests/unit/test_aura_16_stage13_experience.py` covering all outcome types, pattern detection rules, recommendation heuristics, persistence, event bus integration, control plane queries, and Stage 1–12 compatibility.
- **Full Test Suite:** 970 tests passed cleanly across the repository.
