from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from aura.config import ConfigurationManager
from aura.events import (
    EventBus,
    RuntimeAdaptationApplied,
    RuntimeAdaptationApproved,
    RuntimeAdaptationBlocked,
    RuntimeAdaptationExpired,
    RuntimeAdaptationProposed,
    RuntimeAdaptationRejected,
    RuntimeAdaptationRolledBack,
    RuntimeAdaptationValidationFailed,
    RuntimeAdaptationValidationPassed,
)
from aura.logging import get_logger
from aura.memory.store import SQLiteMemoryStore

from .clock import Clock, SystemClock
from .experience import (
    ExperienceRecommendation,
    RecommendationType,
    RuntimeExperienceEngine,
)

if TYPE_CHECKING:
    from .governance import RuntimeGovernanceEngine
    from .resolution import RuntimePolicyEngine

logger = get_logger("RuntimeAdaptivePolicyEngine")


class AdaptationAction(str, Enum):
    """Actions performed within the adaptation lifecycle."""

    PROPOSE = "PROPOSE"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    APPLY = "APPLY"
    ROLLBACK = "ROLLBACK"
    EXPIRE = "EXPIRE"
    BLOCK = "BLOCK"


class AdaptationStatus(str, Enum):
    """Lifecycle operational status of an AdaptationProposal."""

    PROPOSED = "PROPOSED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    VALIDATED = "VALIDATED"
    APPLIED = "APPLIED"
    ROLLED_BACK = "ROLLED_BACK"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


class AdaptationType(str, Enum):
    """Categorization of operational adaptation proposals."""

    REDUCE_FREQUENCY = "REDUCE_FREQUENCY"
    INCREASE_FREQUENCY = "INCREASE_FREQUENCY"
    CHANGE_PRIORITY = "CHANGE_PRIORITY"
    CHANGE_RETRY_POLICY = "CHANGE_RETRY_POLICY"
    CHANGE_OBSERVATION_LEVEL = "CHANGE_OBSERVATION_LEVEL"
    REQUIRE_OPERATOR_REVIEW = "REQUIRE_OPERATOR_REVIEW"
    DISABLE_ACTION = "DISABLE_ACTION"
    ENABLE_ACTION = "ENABLE_ACTION"
    CHANGE_RESOURCE_LIMIT = "CHANGE_RESOURCE_LIMIT"
    NO_CHANGE = "NO_CHANGE"


@dataclass(frozen=True)
class AdaptationProposal:
    """Immutable representation of a proposed runtime operational adaptation."""

    proposal_id: str
    action_id: str
    adaptation_type: AdaptationType
    current_value: Any
    proposed_value: Any
    reason: str
    source_recommendation: str
    source_experience_count: int
    confidence: str
    created_at: str
    expires_at: str
    status: AdaptationStatus = AdaptationStatus.PROPOSED
    requires_operator_approval: bool = True
    safety_constraints: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    previous_value: Any | None = None
    applied_at: str | None = None
    approved_at: str | None = None
    rejected_at: str | None = None
    rolled_back_at: str | None = None
    operator_id: str | None = None


@dataclass(frozen=True)
class AdaptationPolicy:
    """Immutable policy defining hard safety bounds and constraints for adaptations."""

    max_frequency_reduction_percent: float = 50.0
    max_frequency_increase_percent: float = 50.0
    allowed_priorities: tuple[str, ...] = ("LOW", "NORMAL", "HIGH", "CRITICAL")
    max_retry_attempts: int = 5
    min_timeout_seconds: float = 1.0
    max_timeout_seconds: float = 300.0
    protected_actions: tuple[str, ...] = ("system_recovery", "governance_audit")
    always_require_approval_types: tuple[AdaptationType, ...] = (
        AdaptationType.REQUIRE_OPERATOR_REVIEW,
        AdaptationType.DISABLE_ACTION,
        AdaptationType.CHANGE_RETRY_POLICY,
        AdaptationType.CHANGE_RESOURCE_LIMIT,
    )


@dataclass(frozen=True)
class AdaptationValidationResult:
    """Immutable result of adaptation proposal safety validation."""

    valid: bool
    reasons: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OperatorDecision:
    """Immutable record of an explicit human operator approval or rejection."""

    decision_id: str
    proposal_id: str
    operator_id: str
    decision: str  # "APPROVE" or "REJECT"
    reason: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdaptationStatusSnapshot:
    """Immutable diagnostic snapshot of adaptation engine status."""

    total_proposals: int
    pending_approvals: int
    approved: int
    rejected: int
    applied: int
    rolled_back: int
    expired: int
    blocked: int
    validation_failures: int
    last_proposal_at: str | None
    last_application_at: str | None
    last_rollback_at: str | None


class RuntimeAdaptationValidator:
    """Evaluates adaptation proposals against hard safety bounds and governance rules."""

    def __init__(self, policy: AdaptationPolicy | None = None) -> None:
        self.policy = policy or AdaptationPolicy()

    def validate(
        self,
        proposal: AdaptationProposal,
        governance_engine: RuntimeGovernanceEngine | None = None,
        policy_engine: RuntimePolicyEngine | None = None,
        now_iso: str | None = None,
    ) -> AdaptationValidationResult:
        reasons: list[str] = []
        violations: list[str] = []
        warnings: list[str] = []

        # 1. Action Existence & Protection Check
        if not proposal.action_id or not proposal.action_id.strip():
            violations.append("Action ID cannot be empty.")

        if proposal.action_id in self.policy.protected_actions:
            violations.append(f"Action '{proposal.action_id}' is protected and cannot be modified.")

        # 2. Expiration Check
        if proposal.expires_at:
            try:
                exp_dt = datetime.fromisoformat(proposal.expires_at.replace("Z", "+00:00"))
                if now_iso:
                    now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
                elif proposal.created_at:
                    now_dt = datetime.fromisoformat(proposal.created_at.replace("Z", "+00:00"))
                else:
                    now_dt = datetime.now(UTC)

                if now_dt > exp_dt:
                    violations.append(f"Proposal '{proposal.proposal_id}' has expired.")
            except Exception:
                warnings.append("Could not parse expires_at timestamp format.")

        # 3. Adaptation Type Specific Bounds Check
        atype = proposal.adaptation_type
        if atype == AdaptationType.REDUCE_FREQUENCY:
            if (
                isinstance(proposal.proposed_value, (int, float))
                and isinstance(proposal.current_value, (int, float))
                and proposal.current_value > 0
            ):
                pct = (
                    (proposal.current_value - proposal.proposed_value) / proposal.current_value
                ) * 100.0
                if pct > self.policy.max_frequency_reduction_percent:
                    violations.append(
                        f"Frequency reduction ({pct:.1f}%) exceeds maximum allowed "
                        f"({self.policy.max_frequency_reduction_percent}%)."
                    )
        elif atype == AdaptationType.INCREASE_FREQUENCY:
            if (
                isinstance(proposal.proposed_value, (int, float))
                and isinstance(proposal.current_value, (int, float))
                and proposal.current_value > 0
            ):
                pct = (
                    (proposal.proposed_value - proposal.current_value) / proposal.current_value
                ) * 100.0
                if pct > self.policy.max_frequency_increase_percent:
                    violations.append(
                        f"Frequency increase ({pct:.1f}%) exceeds maximum allowed "
                        f"({self.policy.max_frequency_increase_percent}%)."
                    )
        elif atype == AdaptationType.CHANGE_PRIORITY:
            if (
                isinstance(proposal.proposed_value, str)
                and proposal.proposed_value.upper() not in self.policy.allowed_priorities
            ):
                violations.append(
                    f"Proposed priority '{proposal.proposed_value}' not in allowed list "
                    f"{self.policy.allowed_priorities}."
                )
        elif atype == AdaptationType.CHANGE_RETRY_POLICY:
            if (
                isinstance(proposal.proposed_value, int)
                and proposal.proposed_value > self.policy.max_retry_attempts
            ):
                violations.append("Retries exceed max allowed.")

        # 4. Strict Safety Barriers: Prevent Bypass / Escalation / Assurance Tampering
        meta = proposal.metadata or {}
        if (
            meta.get("target_component") in ("governance", "assurance")
            or meta.get("modify_governance")
            or meta.get("modify_assurance")
        ):
            violations.append(
                "Adaptation proposals cannot modify Stage 10 Governance or Stage 15 Assurance."
            )

        if meta.get("escalate_scope") or proposal.proposed_value == "UNRESTRICTED":
            violations.append("Adaptation proposals cannot escalate AutonomyScope.")

        if meta.get("tamper_circuit_breaker") or meta.get("delete_circuit_breaker"):
            violations.append(
                "Adaptation proposals cannot alter or delete CircuitBreakers directly."
            )

        if meta.get("bypass_policy_engine"):
            violations.append("Adaptation proposals cannot bypass Stage 11 PolicyEngine.")

        if meta.get("direct_execution_invocation"):
            violations.append(
                "Adaptation proposals cannot directly invoke Stage 12 ExecutionEngine."
            )

        valid = len(violations) == 0
        if valid:
            reasons.append(
                "Adaptation proposal passed all safety bounds and governance constraints."
            )

        return AdaptationValidationResult(
            valid=valid,
            reasons=reasons,
            violations=violations,
            warnings=warnings,
        )


class RuntimeAdaptationStore:
    """Thread-safe SQLite store for adaptation proposals and operator decisions."""

    def __init__(
        self,
        db_path: str = ":memory:",
        store: SQLiteMemoryStore | None = None,
        container: Any | None = None,
    ) -> None:
        if store is not None:
            self._memory_store = store
            self.db_path = store.db_path
        elif (
            container is not None and hasattr(container, "has") and container.has(SQLiteMemoryStore)
        ):
            self._memory_store = container.resolve(SQLiteMemoryStore)
            self.db_path = self._memory_store.db_path
        else:
            self._memory_store = SQLiteMemoryStore(db_path=db_path)
            self.db_path = db_path

        self._lock: threading.RLock = self._memory_store._lock
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = self._memory_store._get_connection()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_adaptation_proposals (
                        proposal_id TEXT PRIMARY KEY,
                        action_id TEXT NOT NULL,
                        adaptation_type TEXT NOT NULL,
                        current_value TEXT,
                        proposed_value TEXT,
                        reason TEXT NOT NULL,
                        source_recommendation TEXT NOT NULL,
                        source_experience_count INTEGER NOT NULL DEFAULT 0,
                        confidence TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        requires_operator_approval INTEGER NOT NULL DEFAULT 1,
                        safety_constraints TEXT,
                        metadata TEXT,
                        previous_value TEXT,
                        applied_at TEXT,
                        approved_at TEXT,
                        rejected_at TEXT,
                        rolled_back_at TEXT,
                        operator_id TEXT,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_operator_decisions (
                        decision_id TEXT PRIMARY KEY,
                        proposal_id TEXT NOT NULL,
                        operator_id TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        metadata TEXT,
                        FOREIGN KEY(proposal_id)
                            REFERENCES runtime_adaptation_proposals(proposal_id)
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_proposal_action "
                    "ON runtime_adaptation_proposals(action_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_proposal_status "
                    "ON runtime_adaptation_proposals(status);"
                )

    def save_proposal(self, proposal: AdaptationProposal) -> None:
        with self._lock:
            conn = self._memory_store._get_connection()
            now_iso = datetime.now(UTC).isoformat()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runtime_adaptation_proposals (
                        proposal_id, action_id, adaptation_type, current_value, proposed_value,
                        reason, source_recommendation, source_experience_count, confidence,
                        created_at, expires_at, status, requires_operator_approval,
                        safety_constraints, metadata, previous_value, applied_at, approved_at,
                        rejected_at, rolled_back_at, operator_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        proposal.proposal_id,
                        proposal.action_id,
                        proposal.adaptation_type.value,
                        json.dumps(proposal.current_value),
                        json.dumps(proposal.proposed_value),
                        proposal.reason,
                        proposal.source_recommendation,
                        proposal.source_experience_count,
                        proposal.confidence,
                        proposal.created_at,
                        proposal.expires_at,
                        proposal.status.value,
                        1 if proposal.requires_operator_approval else 0,
                        json.dumps(proposal.safety_constraints),
                        json.dumps(proposal.metadata),
                        json.dumps(proposal.previous_value),
                        proposal.applied_at,
                        proposal.approved_at,
                        proposal.rejected_at,
                        proposal.rolled_back_at,
                        proposal.operator_id,
                        now_iso,
                    ),
                )

    def get_proposal(self, proposal_id: str) -> AdaptationProposal | None:
        with self._lock:
            conn = self._memory_store._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT proposal_id, action_id, adaptation_type, current_value, proposed_value,
                       reason, source_recommendation, source_experience_count, confidence,
                       created_at, expires_at, status, requires_operator_approval,
                       safety_constraints, metadata, previous_value, applied_at, approved_at,
                       rejected_at, rolled_back_at, operator_id
                FROM runtime_adaptation_proposals WHERE proposal_id = ?;
                """,
                (proposal_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_proposal(row)

    def get_proposals(
        self,
        action_id: str | None = None,
        status: AdaptationStatus | None = None,
        limit: int = 100,
    ) -> list[AdaptationProposal]:
        with self._lock:
            conn = self._memory_store._get_connection()
            cursor = conn.cursor()
            query = """
                SELECT proposal_id, action_id, adaptation_type, current_value, proposed_value,
                       reason, source_recommendation, source_experience_count, confidence,
                       created_at, expires_at, status, requires_operator_approval,
                       safety_constraints, metadata, previous_value, applied_at, approved_at,
                       rejected_at, rolled_back_at, operator_id
                FROM runtime_adaptation_proposals
            """
            params: list[Any] = []
            conditions: list[str] = []

            if action_id:
                conditions.append("action_id = ?")
                params.append(action_id)
            if status:
                conditions.append("status = ?")
                params.append(status.value)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, tuple(params))
            return [self._row_to_proposal(r) for r in cursor.fetchall()]

    def save_decision(self, decision: OperatorDecision) -> None:
        with self._lock:
            conn = self._memory_store._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runtime_operator_decisions (
                        decision_id, proposal_id, operator_id, decision, reason,
                        created_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        decision.decision_id,
                        decision.proposal_id,
                        decision.operator_id,
                        decision.decision,
                        decision.reason,
                        decision.created_at,
                        json.dumps(decision.metadata),
                    ),
                )

    def count(self, status: AdaptationStatus | None = None) -> int:
        with self._lock:
            conn = self._memory_store._get_connection()
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT COUNT(*) FROM runtime_adaptation_proposals WHERE status = ?;",
                    (status.value,),
                )
            else:
                cursor.execute("SELECT COUNT(*) FROM runtime_adaptation_proposals;")
            res = cursor.fetchone()
            return int(res[0]) if res else 0

    def _row_to_proposal(self, row: tuple[Any, ...]) -> AdaptationProposal:
        return AdaptationProposal(
            proposal_id=row[0],
            action_id=row[1],
            adaptation_type=AdaptationType(row[2]),
            current_value=json.loads(row[3]) if row[3] else None,
            proposed_value=json.loads(row[4]) if row[4] else None,
            reason=row[5],
            source_recommendation=row[6],
            source_experience_count=row[7],
            confidence=row[8],
            created_at=row[9],
            expires_at=row[10],
            status=AdaptationStatus(row[11]),
            requires_operator_approval=bool(row[12]),
            safety_constraints=json.loads(row[13]) if row[13] else {},
            metadata=json.loads(row[14]) if row[14] else {},
            previous_value=json.loads(row[15]) if row[15] else None,
            applied_at=row[16],
            approved_at=row[17],
            rejected_at=row[18],
            rolled_back_at=row[19],
            operator_id=row[20],
        )


class RuntimeAdaptivePolicyEngine:
    """Thread-safe engine for operational adaptations generation and lifecycle."""

    def __init__(
        self,
        store: RuntimeAdaptationStore | None = None,
        validator: RuntimeAdaptationValidator | None = None,
        clock: Clock | None = None,
        event_bus: EventBus | None = None,
        config: ConfigurationManager | None = None,
        experience_engine: RuntimeExperienceEngine | None = None,
        governance_engine: RuntimeGovernanceEngine | None = None,
        policy_engine: RuntimePolicyEngine | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self.store = store or RuntimeAdaptationStore()
        self.validator = validator or RuntimeAdaptationValidator()
        self.clock = clock or SystemClock()
        self.event_bus = event_bus
        self.config = config
        self.experience_engine = experience_engine
        self.governance_engine = governance_engine
        self.policy_engine = policy_engine

        self._validation_failures_count = 0
        self._blocked_count = 0
        self._last_proposal_at: str | None = None
        self._last_application_at: str | None = None
        self._last_rollback_at: str | None = None

    def propose_adaptation(
        self,
        action_id: str,
        adaptation_type: AdaptationType,
        proposed_value: Any,
        reason: str,
        source_recommendation: str = "MANUAL",
        source_experience_count: int = 0,
        confidence: str = "MEDIUM",
        current_value: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> AdaptationProposal:
        with self._lock:
            enabled = True
            ttl_seconds = 3600
            req_approval_default = True

            if self.config:
                enabled = self.config.get_typed("autonomy.adaptation_enabled", bool, True)
                ttl_seconds = self.config.get_typed(
                    "autonomy.adaptation_proposal_ttl_seconds", int, 3600
                )
                req_approval_default = self.config.get_typed(
                    "autonomy.adaptation_require_operator_approval", bool, True
                )

            if not enabled:
                raise RuntimeError("Stage 14 Adaptation Engine is disabled by configuration.")

            now_iso = self.clock.now_iso()
            try:
                now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
            except Exception:
                now_dt = datetime.now(UTC)

            expires_dt = datetime.fromtimestamp(now_dt.timestamp() + ttl_seconds, tz=UTC)
            expires_iso = expires_dt.isoformat()

            pid = f"prop-{action_id}-{now_dt.strftime('%Y%m%d%H%M%S%f')}"

            requires_approval = (
                req_approval_default
                or adaptation_type in self.validator.policy.always_require_approval_types
            )
            initial_status = (
                AdaptationStatus.PENDING_APPROVAL
                if requires_approval
                else AdaptationStatus.PROPOSED
            )

            proposal = AdaptationProposal(
                proposal_id=pid,
                action_id=action_id,
                adaptation_type=adaptation_type,
                current_value=current_value,
                proposed_value=proposed_value,
                reason=reason,
                source_recommendation=source_recommendation,
                source_experience_count=source_experience_count,
                confidence=confidence,
                created_at=now_iso,
                expires_at=expires_iso,
                status=initial_status,
                requires_operator_approval=requires_approval,
                metadata=metadata or {},
            )

            # Validate safety bounds
            val_res = self.validator.validate(
                proposal,
                governance_engine=self.governance_engine,
                policy_engine=self.policy_engine,
                now_iso=now_iso,
            )

            if not val_res.valid:
                self._validation_failures_count += 1
                is_blocked = any(
                    kw in v.lower()
                    for v in val_res.violations
                    for kw in (
                        "governance",
                        "circuit",
                        "scope",
                        "unrestricted",
                        "bypass",
                        "execution",
                        "tamper",
                        "escalate",
                    )
                )
                if is_blocked:
                    self._blocked_count += 1
                    proposal = self._update_proposal_status(proposal, AdaptationStatus.BLOCKED)
                    self.store.save_proposal(proposal)

                    if self.event_bus:
                        self.event_bus.publish(
                            RuntimeAdaptationBlocked(
                                proposal_id=pid,
                                action_id=action_id,
                                reason="; ".join(val_res.violations),
                            )
                        )
                    return proposal

                proposal = self._update_proposal_status(proposal, AdaptationStatus.REJECTED)
                self.store.save_proposal(proposal)

                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeAdaptationValidationFailed(
                            proposal_id=pid,
                            action_id=action_id,
                            violations=val_res.violations,
                        )
                    )
                return proposal

            self.store.save_proposal(proposal)
            self._last_proposal_at = now_iso

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeAdaptationProposed(
                        proposal_id=pid,
                        action_id=action_id,
                        adaptation_type=adaptation_type.value,
                        proposed_value=str(proposed_value),
                        requires_operator_approval=requires_approval,
                    )
                )
                self.event_bus.publish(
                    RuntimeAdaptationValidationPassed(
                        proposal_id=pid,
                        action_id=action_id,
                    )
                )

            return proposal

    def create_proposal_from_recommendation(
        self, recommendation: ExperienceRecommendation
    ) -> AdaptationProposal | None:
        """Adapter helper translating Stage 13 ExperienceRecommendation into AdaptationProposal."""
        with self._lock:
            rec_type = recommendation.recommendation_type
            action_id = recommendation.action_id
            proposed: Any = None

            if rec_type == RecommendationType.REDUCE_FREQUENCY:
                atype = AdaptationType.REDUCE_FREQUENCY
                proposed = 30  # Default frequency reduction proposal
            elif rec_type == RecommendationType.REQUIRE_OPERATOR_REVIEW:
                atype = AdaptationType.REQUIRE_OPERATOR_REVIEW
                proposed = "OPERATOR_REVIEW_REQUIRED"
            elif rec_type == RecommendationType.INVESTIGATE_FAILURE:
                atype = AdaptationType.CHANGE_OBSERVATION_LEVEL
                proposed = "HIGH_OBSERVATION"
            elif rec_type == RecommendationType.KEEP_CURRENT_POLICY:
                atype = AdaptationType.NO_CHANGE
                proposed = "MAINTAIN"
            elif rec_type == RecommendationType.INCREASE_OBSERVATION:
                atype = AdaptationType.CHANGE_OBSERVATION_LEVEL
                proposed = "MONITORING"
            else:
                return None

            return self.propose_adaptation(
                action_id=action_id,
                adaptation_type=atype,
                proposed_value=proposed,
                reason=recommendation.reason,
                source_recommendation=rec_type.value,
                source_experience_count=recommendation.supporting_execution_count,
                confidence=recommendation.confidence.value,
            )

    def approve_proposal(
        self, proposal_id: str, operator_id: str, reason: str
    ) -> AdaptationProposal:
        """Approves a pending adaptation proposal. DOES NOT APPLY automatically."""
        with self._lock:
            proposal = self.store.get_proposal(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal '{proposal_id}' not found.")

            if proposal.status == AdaptationStatus.EXPIRED or self._is_expired(proposal):
                proposal = self._update_proposal_status(proposal, AdaptationStatus.EXPIRED)
                self.store.save_proposal(proposal)
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeAdaptationExpired(
                            proposal_id=proposal_id, action_id=proposal.action_id
                        )
                    )
                raise ValueError(f"Proposal '{proposal_id}' has expired and cannot be approved.")

            if proposal.status == AdaptationStatus.APPROVED:
                return proposal  # Idempotent approval

            if proposal.status not in (
                AdaptationStatus.PENDING_APPROVAL,
                AdaptationStatus.PROPOSED,
            ):
                raise ValueError(
                    f"Proposal '{proposal_id}' in status '{proposal.status}' cannot be approved."
                )

            now_iso = self.clock.now_iso()
            proposal = AdaptationProposal(
                proposal_id=proposal.proposal_id,
                action_id=proposal.action_id,
                adaptation_type=proposal.adaptation_type,
                current_value=proposal.current_value,
                proposed_value=proposal.proposed_value,
                reason=proposal.reason,
                source_recommendation=proposal.source_recommendation,
                source_experience_count=proposal.source_experience_count,
                confidence=proposal.confidence,
                created_at=proposal.created_at,
                expires_at=proposal.expires_at,
                status=AdaptationStatus.APPROVED,
                requires_operator_approval=proposal.requires_operator_approval,
                safety_constraints=proposal.safety_constraints,
                metadata=proposal.metadata,
                previous_value=proposal.previous_value,
                applied_at=proposal.applied_at,
                approved_at=now_iso,
                rejected_at=proposal.rejected_at,
                rolled_back_at=proposal.rolled_back_at,
                operator_id=operator_id,
            )

            self.store.save_proposal(proposal)

            decision = OperatorDecision(
                decision_id=f"dec-{proposal_id}-{now_iso}",
                proposal_id=proposal_id,
                operator_id=operator_id,
                decision="APPROVE",
                reason=reason,
                created_at=now_iso,
            )
            self.store.save_decision(decision)

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeAdaptationApproved(
                        proposal_id=proposal_id,
                        action_id=proposal.action_id,
                        operator_id=operator_id,
                    )
                )

            return proposal

    def reject_proposal(
        self, proposal_id: str, operator_id: str, reason: str
    ) -> AdaptationProposal:
        """Rejects a pending adaptation proposal."""
        with self._lock:
            proposal = self.store.get_proposal(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal '{proposal_id}' not found.")

            if proposal.status == AdaptationStatus.REJECTED:
                return proposal  # Idempotent rejection

            now_iso = self.clock.now_iso()
            proposal = AdaptationProposal(
                proposal_id=proposal.proposal_id,
                action_id=proposal.action_id,
                adaptation_type=proposal.adaptation_type,
                current_value=proposal.current_value,
                proposed_value=proposal.proposed_value,
                reason=proposal.reason,
                source_recommendation=proposal.source_recommendation,
                source_experience_count=proposal.source_experience_count,
                confidence=proposal.confidence,
                created_at=proposal.created_at,
                expires_at=proposal.expires_at,
                status=AdaptationStatus.REJECTED,
                requires_operator_approval=proposal.requires_operator_approval,
                safety_constraints=proposal.safety_constraints,
                metadata=proposal.metadata,
                previous_value=proposal.previous_value,
                applied_at=proposal.applied_at,
                approved_at=proposal.approved_at,
                rejected_at=now_iso,
                rolled_back_at=proposal.rolled_back_at,
                operator_id=operator_id,
            )

            self.store.save_proposal(proposal)

            decision = OperatorDecision(
                decision_id=f"dec-rej-{proposal_id}-{now_iso}",
                proposal_id=proposal_id,
                operator_id=operator_id,
                decision="REJECT",
                reason=reason,
                created_at=now_iso,
            )
            self.store.save_decision(decision)

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeAdaptationRejected(
                        proposal_id=proposal_id,
                        action_id=proposal.action_id,
                        operator_id=operator_id,
                        reason=reason,
                    )
                )

            return proposal

    def apply_adaptation(self, proposal_id: str) -> AdaptationProposal:
        """Applies an approved adaptation proposal idempotently."""
        with self._lock:
            proposal = self.store.get_proposal(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal '{proposal_id}' not found.")

            if proposal.status == AdaptationStatus.APPLIED:
                return proposal  # Idempotent re-application

            if self._is_expired(proposal):
                proposal = self._update_proposal_status(proposal, AdaptationStatus.EXPIRED)
                self.store.save_proposal(proposal)
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeAdaptationExpired(
                            proposal_id=proposal_id, action_id=proposal.action_id
                        )
                    )
                raise ValueError(f"Proposal '{proposal_id}' has expired and cannot be applied.")

            if proposal.requires_operator_approval and proposal.status != AdaptationStatus.APPROVED:
                raise PermissionError(
                    f"Proposal '{proposal_id}' requires explicit operator approval "
                    "before application."
                )

            # Re-validate safety bounds immediately prior to execution
            val_res = self.validator.validate(
                proposal,
                governance_engine=self.governance_engine,
                policy_engine=self.policy_engine,
            )
            if not val_res.valid:
                proposal = self._update_proposal_status(proposal, AdaptationStatus.BLOCKED)
                self.store.save_proposal(proposal)
                self._blocked_count += 1
                if self.event_bus:
                    self.event_bus.publish(
                        RuntimeAdaptationBlocked(
                            proposal_id=proposal_id,
                            action_id=proposal.action_id,
                            reason="; ".join(val_res.violations),
                        )
                    )
                raise ValueError(
                    f"Proposal '{proposal_id}' safety validation failed prior to apply."
                )

            now_iso = self.clock.now_iso()
            proposal = AdaptationProposal(
                proposal_id=proposal.proposal_id,
                action_id=proposal.action_id,
                adaptation_type=proposal.adaptation_type,
                current_value=proposal.current_value,
                proposed_value=proposal.proposed_value,
                reason=proposal.reason,
                source_recommendation=proposal.source_recommendation,
                source_experience_count=proposal.source_experience_count,
                confidence=proposal.confidence,
                created_at=proposal.created_at,
                expires_at=proposal.expires_at,
                status=AdaptationStatus.APPLIED,
                requires_operator_approval=proposal.requires_operator_approval,
                safety_constraints=proposal.safety_constraints,
                metadata=proposal.metadata,
                previous_value=proposal.current_value,
                applied_at=now_iso,
                approved_at=proposal.approved_at,
                rejected_at=proposal.rejected_at,
                rolled_back_at=proposal.rolled_back_at,
                operator_id=proposal.operator_id,
            )

            self.store.save_proposal(proposal)
            self._last_application_at = now_iso

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeAdaptationApplied(
                        proposal_id=proposal_id,
                        action_id=proposal.action_id,
                        applied_value=str(proposal.proposed_value),
                    )
                )

            return proposal

    def rollback_adaptation(self, proposal_id: str) -> AdaptationProposal:
        """Rolls back an applied adaptation proposal idempotently."""
        with self._lock:
            proposal = self.store.get_proposal(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal '{proposal_id}' not found.")

            if proposal.status == AdaptationStatus.ROLLED_BACK:
                return proposal  # Idempotent rollback

            if proposal.status != AdaptationStatus.APPLIED:
                raise ValueError(
                    f"Proposal '{proposal_id}' in status '{proposal.status}' cannot be rolled back."
                )

            now_iso = self.clock.now_iso()
            proposal = AdaptationProposal(
                proposal_id=proposal.proposal_id,
                action_id=proposal.action_id,
                adaptation_type=proposal.adaptation_type,
                current_value=proposal.proposed_value,
                proposed_value=proposal.previous_value,
                reason=f"Rollback of proposal {proposal_id}",
                source_recommendation=proposal.source_recommendation,
                source_experience_count=proposal.source_experience_count,
                confidence=proposal.confidence,
                created_at=proposal.created_at,
                expires_at=proposal.expires_at,
                status=AdaptationStatus.ROLLED_BACK,
                requires_operator_approval=proposal.requires_operator_approval,
                safety_constraints=proposal.safety_constraints,
                metadata=proposal.metadata,
                previous_value=proposal.current_value,
                applied_at=proposal.applied_at,
                approved_at=proposal.approved_at,
                rejected_at=proposal.rejected_at,
                rolled_back_at=now_iso,
                operator_id=proposal.operator_id,
            )

            self.store.save_proposal(proposal)
            self._last_rollback_at = now_iso

            if self.event_bus:
                self.event_bus.publish(
                    RuntimeAdaptationRolledBack(
                        proposal_id=proposal_id,
                        action_id=proposal.action_id,
                        restored_value=str(proposal.previous_value),
                    )
                )

            return proposal

    def get_adaptation_snapshot(self) -> AdaptationStatusSnapshot:
        """Returns an immutable diagnostic snapshot of the adaptation engine state."""
        with self._lock:
            all_props = self.store.get_proposals(limit=10000)
            total = len(all_props)
            pending = sum(
                1
                for p in all_props
                if p.status in (AdaptationStatus.PENDING_APPROVAL, AdaptationStatus.PROPOSED)
            )
            approved = sum(1 for p in all_props if p.status == AdaptationStatus.APPROVED)
            rejected = sum(1 for p in all_props if p.status == AdaptationStatus.REJECTED)
            applied = sum(1 for p in all_props if p.status == AdaptationStatus.APPLIED)
            rolled_back = sum(1 for p in all_props if p.status == AdaptationStatus.ROLLED_BACK)
            expired = sum(1 for p in all_props if p.status == AdaptationStatus.EXPIRED)
            blocked = sum(1 for p in all_props if p.status == AdaptationStatus.BLOCKED)

            return AdaptationStatusSnapshot(
                total_proposals=total,
                pending_approvals=pending,
                approved=approved,
                rejected=rejected,
                applied=applied,
                rolled_back=rolled_back,
                expired=expired,
                blocked=blocked + self._blocked_count,
                validation_failures=self._validation_failures_count,
                last_proposal_at=self._last_proposal_at,
                last_application_at=self._last_application_at,
                last_rollback_at=self._last_rollback_at,
            )

    def _is_expired(self, proposal: AdaptationProposal) -> bool:
        if not proposal.expires_at:
            return False
        try:
            exp_dt = datetime.fromisoformat(proposal.expires_at.replace("Z", "+00:00"))
            now_iso = self.clock.now_iso()
            now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        except Exception:
            return False
        return now_dt > exp_dt

    def _update_proposal_status(
        self, proposal: AdaptationProposal, status: AdaptationStatus
    ) -> AdaptationProposal:
        return AdaptationProposal(
            proposal_id=proposal.proposal_id,
            action_id=proposal.action_id,
            adaptation_type=proposal.adaptation_type,
            current_value=proposal.current_value,
            proposed_value=proposal.proposed_value,
            reason=proposal.reason,
            source_recommendation=proposal.source_recommendation,
            source_experience_count=proposal.source_experience_count,
            confidence=proposal.confidence,
            created_at=proposal.created_at,
            expires_at=proposal.expires_at,
            status=status,
            requires_operator_approval=proposal.requires_operator_approval,
            safety_constraints=proposal.safety_constraints,
            metadata=proposal.metadata,
            previous_value=proposal.previous_value,
            applied_at=proposal.applied_at,
            approved_at=proposal.approved_at,
            rejected_at=proposal.rejected_at,
            rolled_back_at=proposal.rolled_back_at,
            operator_id=proposal.operator_id,
        )
