from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from aura.config import ConfigurationManager
from aura.events import (
    EventBus,
    RuntimeExecutionCancelled,
    RuntimeExecutionCompensated,
    RuntimeExecutionCompleted,
    RuntimeExecutionFailed,
    RuntimeExecutionRolledBack,
    RuntimeExecutionTimedOut,
    RuntimeExperienceUpdated,
    RuntimeFailurePatternDetected,
    RuntimeOperatorReviewRecommended,
    RuntimeOutcomeRecorded,
    RuntimeRecommendationGenerated,
)
from aura.logging import get_logger
from aura.memory.store import SQLiteMemoryStore

from .clock import Clock, SystemClock
from .execution import ExecutionResult, ExecutionState

logger = get_logger("RuntimeExperience")


class OutcomeType(str, Enum):
    """Classification of execution outcomes for experience tracking."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    ROLLED_BACK = "ROLLED_BACK"
    COMPENSATED = "COMPENSATED"
    BLOCKED = "BLOCKED"
    DEFERRED = "DEFERRED"


class ExperienceConfidence(str, Enum):
    """Confidence rating of statistical experience data."""

    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class RecommendationType(str, Enum):
    """Supported adaptive decision support recommendations."""

    RETRY = "RETRY"
    DEFER = "DEFER"
    REDUCE_FREQUENCY = "REDUCE_FREQUENCY"
    INCREASE_OBSERVATION = "INCREASE_OBSERVATION"
    INVESTIGATE_FAILURE = "INVESTIGATE_FAILURE"
    KEEP_CURRENT_POLICY = "KEEP_CURRENT_POLICY"
    REQUIRE_OPERATOR_REVIEW = "REQUIRE_OPERATOR_REVIEW"


@dataclass(frozen=True)
class OutcomeRecord:
    """Immutable record representing a historical action execution outcome."""

    execution_id: str
    action_id: str
    schedule_id: str | None = None
    goal_id: str | None = None
    outcome_type: OutcomeType = OutcomeType.SUCCESS
    success: bool = True
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    attempt_count: int = 1
    failure_type: str | None = None
    error: str | None = None
    rollback_performed: bool = False
    compensation_performed: bool = False
    governance_scope: str | None = None
    policy_action: str | None = None
    resources: tuple[str, ...] = ()
    idempotency_key: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Converts outcome record to a plain JSON-serializable dictionary."""
        return {
            "execution_id": self.execution_id,
            "action_id": self.action_id,
            "schedule_id": self.schedule_id,
            "goal_id": self.goal_id,
            "outcome_type": self.outcome_type.value,
            "success": self.success,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "attempt_count": self.attempt_count,
            "failure_type": self.failure_type,
            "error": self.error,
            "rollback_performed": self.rollback_performed,
            "compensation_performed": self.compensation_performed,
            "governance_scope": self.governance_scope,
            "policy_action": self.policy_action,
            "resources": list(self.resources),
            "idempotency_key": self.idempotency_key,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ActionExperience:
    """Immutable aggregated historical metrics and statistics for a specific action."""

    action_id: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    cancelled_executions: int = 0
    timeout_executions: int = 0
    rollback_executions: int = 0
    compensation_executions: int = 0
    success_rate: float = 0.0
    failure_rate: float = 0.0
    average_duration_seconds: float = 0.0
    last_execution_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    confidence: ExperienceConfidence = ExperienceConfidence.UNKNOWN
    last_failure_type: str | None = None
    common_failure_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExperienceRecommendation:
    """Immutable decision support recommendation generated deterministically."""

    action_id: str
    recommendation_type: RecommendationType
    confidence: ExperienceConfidence
    reason: str
    supporting_execution_count: int
    generated_at: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExperienceStatusSnapshot:
    """Immutable diagnostic snapshot of runtime experience system status."""

    total_outcomes: int = 0
    successful_outcomes: int = 0
    failed_outcomes: int = 0
    timeout_outcomes: int = 0
    rollback_outcomes: int = 0
    compensation_outcomes: int = 0
    tracked_actions: int = 0
    recommendations_generated: int = 0
    failure_patterns_detected: int = 0
    last_outcome_at: str | None = None


class RuntimeExperienceStore:
    """Thread-safe SQLite persistent store for outcome history and experience records."""

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

    def _get_connection(self) -> sqlite3.Connection:
        return self._memory_store._get_connection()

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_outcome_history (
                        execution_id TEXT PRIMARY KEY,
                        action_id TEXT NOT NULL,
                        schedule_id TEXT,
                        goal_id TEXT,
                        outcome_type TEXT NOT NULL,
                        success INTEGER NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT NOT NULL,
                        duration_seconds REAL NOT NULL,
                        attempt_count INTEGER NOT NULL,
                        failure_type TEXT,
                        error TEXT,
                        rollback_performed INTEGER NOT NULL,
                        compensation_performed INTEGER NOT NULL,
                        governance_scope TEXT,
                        policy_action TEXT,
                        resources TEXT NOT NULL,
                        idempotency_key TEXT,
                        metadata TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_outcome_action_id "
                    "ON runtime_outcome_history(action_id);"
                )

    def record_outcome(self, record: OutcomeRecord) -> None:
        """Atomically inserts or replaces an OutcomeRecord in SQLite."""
        with self._lock:
            conn = self._get_connection()
            created_at = datetime.now(UTC).isoformat()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runtime_outcome_history (
                        execution_id, action_id, schedule_id, goal_id, outcome_type,
                        success, started_at, completed_at, duration_seconds, attempt_count,
                        failure_type, error, rollback_performed, compensation_performed,
                        governance_scope, policy_action, resources, idempotency_key,
                        metadata, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        record.execution_id,
                        record.action_id,
                        record.schedule_id,
                        record.goal_id,
                        record.outcome_type.value,
                        1 if record.success else 0,
                        record.started_at,
                        record.completed_at,
                        record.duration_seconds,
                        record.attempt_count,
                        record.failure_type,
                        record.error,
                        1 if record.rollback_performed else 0,
                        1 if record.compensation_performed else 0,
                        record.governance_scope,
                        record.policy_action,
                        json.dumps(list(record.resources)),
                        record.idempotency_key,
                        json.dumps(dict(record.metadata)),
                        created_at,
                    ),
                )

    def get_outcome(self, execution_id: str) -> OutcomeRecord | None:
        """Retrieves a single OutcomeRecord by execution_id."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM runtime_outcome_history WHERE execution_id = ?",
                (execution_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_outcome(row)

    def get_recent_outcomes(
        self, action_id: str | None = None, limit: int = 100
    ) -> list[OutcomeRecord]:
        """Retrieves recent outcomes sorted by creation order descending."""
        with self._lock:
            conn = self._get_connection()
            if action_id is not None:
                cursor = conn.execute(
                    "SELECT * FROM runtime_outcome_history WHERE action_id = ? "
                    "ORDER BY rowid DESC LIMIT ?",
                    (action_id, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM runtime_outcome_history ORDER BY rowid DESC LIMIT ?",
                    (limit,),
                )
            rows = cursor.fetchall()
            return [self._row_to_outcome(r) for r in rows]

    def get_failures(self, action_id: str | None = None, limit: int = 100) -> list[OutcomeRecord]:
        """Retrieves failed outcomes (success = 0) sorted descending."""
        with self._lock:
            conn = self._get_connection()
            if action_id is not None:
                cursor = conn.execute(
                    "SELECT * FROM runtime_outcome_history WHERE action_id = ? AND success = 0 "
                    "ORDER BY rowid DESC LIMIT ?",
                    (action_id, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM runtime_outcome_history WHERE success = 0 "
                    "ORDER BY rowid DESC LIMIT ?",
                    (limit,),
                )
            return [self._row_to_outcome(r) for r in cursor.fetchall()]

    def get_successes(self, action_id: str | None = None, limit: int = 100) -> list[OutcomeRecord]:
        """Retrieves successful outcomes (success = 1) sorted descending."""
        with self._lock:
            conn = self._get_connection()
            if action_id is not None:
                cursor = conn.execute(
                    "SELECT * FROM runtime_outcome_history WHERE action_id = ? AND success = 1 "
                    "ORDER BY rowid DESC LIMIT ?",
                    (action_id, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM runtime_outcome_history WHERE success = 1 "
                    "ORDER BY rowid DESC LIMIT ?",
                    (limit,),
                )
            return [self._row_to_outcome(r) for r in cursor.fetchall()]

    def get_action_experience(self, action_id: str) -> ActionExperience:
        """Calculates ActionExperience deterministically from historical outcome records."""
        with self._lock:
            outcomes = self.get_recent_outcomes(action_id=action_id, limit=1000)
            if not outcomes:
                return ActionExperience(
                    action_id=action_id,
                    confidence=ExperienceConfidence.UNKNOWN,
                )

            # Sort chronologically ascending for sequential analysis
            chronological = list(reversed(outcomes))
            total = len(chronological)
            successful = sum(1 for o in chronological if o.success)
            failed = sum(1 for o in chronological if not o.success)
            cancelled = sum(1 for o in chronological if o.outcome_type == OutcomeType.CANCELLED)
            timed_out = sum(1 for o in chronological if o.outcome_type == OutcomeType.TIMED_OUT)
            rollbacks = sum(1 for o in chronological if o.rollback_performed)
            compensations = sum(1 for o in chronological if o.compensation_performed)

            success_rate = successful / total if total > 0 else 0.0
            failure_rate = failed / total if total > 0 else 0.0
            avg_duration = sum(o.duration_seconds for o in chronological) / total

            last_exec = chronological[-1].completed_at or chronological[-1].started_at
            last_succ = next((o.completed_at for o in reversed(chronological) if o.success), None)
            last_fail = next(
                (o.completed_at for o in reversed(chronological) if not o.success), None
            )

            # Consecutive calculations
            consecutive_failures = 0
            for o in reversed(chronological):
                if not o.success:
                    consecutive_failures += 1
                else:
                    break

            consecutive_successes = 0
            for o in reversed(chronological):
                if o.success:
                    consecutive_successes += 1
                else:
                    break

            # Failure type aggregation
            failure_types = [
                o.failure_type for o in chronological if not o.success and o.failure_type
            ]
            last_failure_type = failure_types[-1] if failure_types else None
            counts: dict[str, int] = {}
            for ft in failure_types:
                counts[ft] = counts.get(ft, 0) + 1
            sorted_types = tuple(
                k for k, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)
            )

            # Confidence determination based on sample size
            if total >= 25:
                confidence = ExperienceConfidence.VERY_HIGH
            elif total >= 10:
                confidence = ExperienceConfidence.HIGH
            elif total >= 3:
                confidence = ExperienceConfidence.MEDIUM
            else:
                confidence = ExperienceConfidence.LOW

            return ActionExperience(
                action_id=action_id,
                total_executions=total,
                successful_executions=successful,
                failed_executions=failed,
                cancelled_executions=cancelled,
                timeout_executions=timed_out,
                rollback_executions=rollbacks,
                compensation_executions=compensations,
                success_rate=success_rate,
                failure_rate=failure_rate,
                average_duration_seconds=avg_duration,
                last_execution_at=last_exec,
                last_success_at=last_succ,
                last_failure_at=last_fail,
                consecutive_failures=consecutive_failures,
                consecutive_successes=consecutive_successes,
                confidence=confidence,
                last_failure_type=last_failure_type,
                common_failure_types=sorted_types,
            )

    def count(self, action_id: str | None = None) -> int:
        """Returns count of recorded outcomes."""
        with self._lock:
            conn = self._get_connection()
            if action_id is not None:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM runtime_outcome_history WHERE action_id = ?",
                    (action_id,),
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM runtime_outcome_history")
            row = cursor.fetchone()
            return row[0] if row else 0

    def clear_history(self, action_id: str | None = None) -> int:
        """Clears outcome history atomically."""
        with self._lock:
            conn = self._get_connection()
            with conn:
                if action_id is not None:
                    cursor = conn.execute(
                        "DELETE FROM runtime_outcome_history WHERE action_id = ?",
                        (action_id,),
                    )
                else:
                    cursor = conn.execute("DELETE FROM runtime_outcome_history")
                return cursor.rowcount

    @staticmethod
    def _row_to_outcome(row: sqlite3.Row) -> OutcomeRecord:
        resources = tuple(json.loads(row["resources"]))
        metadata = json.loads(row["metadata"])
        return OutcomeRecord(
            execution_id=row["execution_id"],
            action_id=row["action_id"],
            schedule_id=row["schedule_id"],
            goal_id=row["goal_id"],
            outcome_type=OutcomeType(row["outcome_type"]),
            success=bool(row["success"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            duration_seconds=float(row["duration_seconds"]),
            attempt_count=int(row["attempt_count"]),
            failure_type=row["failure_type"],
            error=row["error"],
            rollback_performed=bool(row["rollback_performed"]),
            compensation_performed=bool(row["compensation_performed"]),
            governance_scope=row["governance_scope"],
            policy_action=row["policy_action"],
            resources=resources,
            idempotency_key=row["idempotency_key"],
            metadata=metadata,
        )


class RuntimeExperienceEngine:
    """Thread-safe engine for outcome recording and decision support."""

    def __init__(
        self,
        store: RuntimeExperienceStore | None = None,
        clock: Clock | None = None,
        event_bus: EventBus | None = None,
        config: ConfigurationManager | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self.store = store or RuntimeExperienceStore()
        self.clock = clock or SystemClock()
        self.event_bus = event_bus
        self.config = config
        self._recommendations: dict[str, ExperienceRecommendation] = {}
        self._detected_patterns: list[dict[str, Any]] = []

        self._recommendations_generated_count = 0
        self._failure_patterns_count = 0

        if self.event_bus:
            self._subscribe_events()

    def _subscribe_events(self) -> None:
        """Subscribes exclusively to Stage 12 execution events to record outcomes."""
        if not self.event_bus:
            return

        self.event_bus.subscribe(RuntimeExecutionCompleted, self._on_execution_completed)
        self.event_bus.subscribe(RuntimeExecutionFailed, self._on_execution_failed)
        self.event_bus.subscribe(RuntimeExecutionRolledBack, self._on_execution_rolled_back)
        self.event_bus.subscribe(RuntimeExecutionCompensated, self._on_execution_compensated)
        self.event_bus.subscribe(RuntimeExecutionCancelled, self._on_execution_cancelled)
        self.event_bus.subscribe(RuntimeExecutionTimedOut, self._on_execution_timed_out)

    def record_outcome(self, record: OutcomeRecord) -> ExperienceRecommendation | None:
        """Records an outcome, updates metrics, detects patterns & returns recommendation."""
        with self._lock:
            enabled = True
            if self.config:
                enabled = self.config.get_typed("autonomy.experience_enabled", bool, True)
            if not enabled:
                return None

            # Persist outcome record
            self.store.record_outcome(record)

            # Publish RuntimeOutcomeRecorded event
            if self.event_bus:
                try:
                    self.event_bus.publish(
                        RuntimeOutcomeRecorded(
                            execution_id=record.execution_id,
                            action_id=record.action_id,
                            outcome_type=record.outcome_type.value,
                            success=record.success,
                        )
                    )
                except Exception as exc:
                    logger.warning(f"Failed to publish RuntimeOutcomeRecorded: {exc}")

            # Re-calculate action experience metrics
            exp = self.store.get_action_experience(record.action_id)

            if self.event_bus:
                try:
                    self.event_bus.publish(
                        RuntimeExperienceUpdated(
                            action_id=exp.action_id,
                            total_executions=exp.total_executions,
                            success_rate=exp.success_rate,
                            confidence=exp.confidence.value,
                        )
                    )
                except Exception as exc:
                    logger.warning(f"Failed to publish RuntimeExperienceUpdated: {exc}")

            # Pattern Detection & Recommendation Generation
            self.detect_failure_patterns(record.action_id)
            rec = self.generate_recommendation(record.action_id)

            if rec:
                self._recommendations[record.action_id] = rec
                self._recommendations_generated_count += 1
                if self.event_bus:
                    try:
                        self.event_bus.publish(
                            RuntimeRecommendationGenerated(
                                action_id=rec.action_id,
                                recommendation_type=rec.recommendation_type.value,
                                confidence=rec.confidence.value,
                                reason=rec.reason,
                            )
                        )
                        if rec.recommendation_type == RecommendationType.REQUIRE_OPERATOR_REVIEW:
                            self.event_bus.publish(
                                RuntimeOperatorReviewRecommended(
                                    action_id=rec.action_id,
                                    reason=rec.reason,
                                    consecutive_failures=exp.consecutive_failures,
                                    failure_rate=exp.failure_rate,
                                )
                            )
                    except Exception as exc:
                        logger.warning(f"Failed to publish recommendation events: {exc}")

            return rec

    def record_execution_result(
        self, result: ExecutionResult, action_id: str, schedule_id: str | None = None
    ) -> ExperienceRecommendation | None:
        """Adapter helper to convert a Stage 12 ExecutionResult into an OutcomeRecord."""
        with self._lock:
            # Map ExecutionState to OutcomeType
            if result.state == ExecutionState.COMMITTED:
                out_type = OutcomeType.SUCCESS
            elif result.state == ExecutionState.COMPENSATED:
                out_type = OutcomeType.COMPENSATED
            elif result.state == ExecutionState.ROLLED_BACK:
                out_type = OutcomeType.ROLLED_BACK
            elif result.state == ExecutionState.TIMED_OUT:
                out_type = OutcomeType.TIMED_OUT
            elif result.state == ExecutionState.CANCELLED:
                out_type = OutcomeType.CANCELLED
            else:
                out_type = OutcomeType.FAILURE

            duration = 0.0
            if result.started_at and result.completed_at:
                try:
                    dt1 = datetime.fromisoformat(result.started_at.replace("Z", "+00:00"))
                    dt2 = datetime.fromisoformat(result.completed_at.replace("Z", "+00:00"))
                    duration = max(0.0, (dt2 - dt1).total_seconds())
                except Exception:
                    duration = 0.0

            record = OutcomeRecord(
                execution_id=result.execution_id,
                action_id=action_id,
                schedule_id=result.schedule_id,
                goal_id=result.goal_id,
                outcome_type=out_type,
                success=result.success,
                started_at=result.started_at,
                completed_at=result.completed_at,
                duration_seconds=duration,
                attempt_count=result.attempt_number,
                failure_type=result.failure_type.value if result.failure_type else None,
                error=result.error,
                rollback_performed=result.rollback_performed,
                compensation_performed=result.compensation_performed,
                idempotency_key=result.idempotency_key,
                metadata=result.output if isinstance(result.output, dict) else {},
            )
            return self.record_outcome(record)

    def detect_failure_patterns(self, action_id: str) -> list[dict[str, Any]]:
        """Detects deterministic failure patterns based on statistical rules without ML."""
        with self._lock:
            exp = self.store.get_action_experience(action_id)
            outcomes = self.store.get_recent_outcomes(action_id=action_id, limit=20)
            patterns: list[dict[str, Any]] = []

            fail_threshold = 3
            timeout_threshold = 3
            review_threshold = 0.50

            if self.config:
                fail_threshold = self.config.get_typed(
                    "autonomy.experience_failure_threshold", int, 3
                )
                timeout_threshold = self.config.get_typed(
                    "autonomy.experience_timeout_threshold", int, 3
                )
                review_threshold = self.config.get_typed(
                    "autonomy.experience_review_threshold", float, 0.50
                )

            # 1. Consecutive Failures Pattern
            if exp.consecutive_failures >= fail_threshold:
                pat = {
                    "action_id": action_id,
                    "pattern_type": "CONSECUTIVE_FAILURES",
                    "details": f"{exp.consecutive_failures} consecutive failures detected",
                    "count": exp.consecutive_failures,
                }
                patterns.append(pat)

            # 2. Repeated Failure Type Pattern
            if exp.common_failure_types:
                top_ft = exp.common_failure_types[0]
                same_ft_count = sum(
                    1 for o in outcomes if not o.success and o.failure_type == top_ft
                )
                if same_ft_count >= 2:
                    pat = {
                        "action_id": action_id,
                        "pattern_type": "REPEATED_FAILURE_TYPE",
                        "details": f"Failure type '{top_ft}' repeated {same_ft_count} times",
                        "count": same_ft_count,
                    }
                    patterns.append(pat)

            # 3. Timeout Pattern
            if exp.timeout_executions >= timeout_threshold:
                pat = {
                    "action_id": action_id,
                    "pattern_type": "TIMEOUT_PATTERN",
                    "details": f"{exp.timeout_executions} execution timeouts recorded",
                    "count": exp.timeout_executions,
                }
                patterns.append(pat)

            # 4. Rollback Pattern
            if exp.rollback_executions >= 2:
                pat = {
                    "action_id": action_id,
                    "pattern_type": "ROLLBACK_PATTERN",
                    "details": f"{exp.rollback_executions} executions required rollback",
                    "count": exp.rollback_executions,
                }
                patterns.append(pat)

            # 5. Compensation Pattern
            if exp.compensation_executions >= 1:
                pat = {
                    "action_id": action_id,
                    "pattern_type": "COMPENSATION_PATTERN",
                    "details": (
                        f"{exp.compensation_executions} executions required failure compensation"
                    ),
                    "count": exp.compensation_executions,
                }
                patterns.append(pat)

            # 6. Degradation Pattern
            if exp.total_executions >= 5 and exp.failure_rate >= review_threshold:
                pat = {
                    "action_id": action_id,
                    "pattern_type": "DEGRADATION_PATTERN",
                    "details": (
                        f"High failure rate ({exp.failure_rate:.1%}) "
                        f"across {exp.total_executions} executions"
                    ),
                    "count": exp.failed_executions,
                }
                patterns.append(pat)

            if patterns:
                self._failure_patterns_count += len(patterns)
                self._detected_patterns.extend(patterns)
                if self.event_bus:
                    for p in patterns:
                        try:
                            self.event_bus.publish(
                                RuntimeFailurePatternDetected(
                                    action_id=action_id,
                                    pattern_type=p["pattern_type"],
                                    details=p["details"],
                                )
                            )
                        except Exception as exc:
                            logger.warning(
                                f"Failed to publish RuntimeFailurePatternDetected: {exc}"
                            )

            return patterns

    def generate_recommendation(self, action_id: str) -> ExperienceRecommendation | None:
        """Generates an explainable ExperienceRecommendation deterministically."""
        with self._lock:
            recs_enabled = True
            if self.config:
                recs_enabled = self.config.get_typed(
                    "autonomy.experience_recommendations_enabled", bool, True
                )
            if not recs_enabled:
                return None

            exp = self.store.get_action_experience(action_id)
            now_iso = self.clock.now_iso()

            fail_threshold = 3
            timeout_threshold = 3
            review_threshold = 0.50
            if self.config:
                fail_threshold = self.config.get_typed(
                    "autonomy.experience_failure_threshold", int, 3
                )
                timeout_threshold = self.config.get_typed(
                    "autonomy.experience_timeout_threshold", int, 3
                )
                review_threshold = self.config.get_typed(
                    "autonomy.experience_review_threshold", float, 0.50
                )

            # Rule 1: High failure rate or consecutive failures -> REQUIRE_OPERATOR_REVIEW
            if exp.consecutive_failures >= fail_threshold or (
                exp.total_executions >= 5 and exp.failure_rate >= review_threshold
            ):
                return ExperienceRecommendation(
                    action_id=action_id,
                    recommendation_type=RecommendationType.REQUIRE_OPERATOR_REVIEW,
                    confidence=exp.confidence,
                    reason=(
                        f"Action '{action_id}' has {exp.consecutive_failures} consecutive failures "
                        f"and failure rate of {exp.failure_rate:.1%}. Operator review recommended."
                    ),
                    supporting_execution_count=exp.total_executions,
                    generated_at=now_iso,
                    metadata={"consecutive_failures": exp.consecutive_failures},
                )

            # Rule 2: Repeated Timeouts -> REDUCE_FREQUENCY
            if exp.timeout_executions >= timeout_threshold:
                return ExperienceRecommendation(
                    action_id=action_id,
                    recommendation_type=RecommendationType.REDUCE_FREQUENCY,
                    confidence=exp.confidence,
                    reason=(
                        f"Action '{action_id}' experienced {exp.timeout_executions} timeouts. "
                        "Reducing scheduling frequency recommended."
                    ),
                    supporting_execution_count=exp.total_executions,
                    generated_at=now_iso,
                )

            # Rule 3: Rollbacks or Compensations -> INVESTIGATE_FAILURE
            if exp.rollback_executions >= 2 or exp.compensation_executions >= 1:
                return ExperienceRecommendation(
                    action_id=action_id,
                    recommendation_type=RecommendationType.INVESTIGATE_FAILURE,
                    confidence=exp.confidence,
                    reason=(
                        f"Action '{action_id}' triggered {exp.rollback_executions} rollbacks "
                        f"and {exp.compensation_executions} compensations. "
                        "Investigation recommended."
                    ),
                    supporting_execution_count=exp.total_executions,
                    generated_at=now_iso,
                )

            # Rule 4: High success rate -> KEEP_CURRENT_POLICY
            if exp.total_executions >= 3 and exp.success_rate >= 0.80:
                return ExperienceRecommendation(
                    action_id=action_id,
                    recommendation_type=RecommendationType.KEEP_CURRENT_POLICY,
                    confidence=exp.confidence,
                    reason=(
                        f"Action '{action_id}' exhibits high success rate ({exp.success_rate:.1%}) "
                        f"across {exp.total_executions} runs. Current policy optimal."
                    ),
                    supporting_execution_count=exp.total_executions,
                    generated_at=now_iso,
                )

            # Rule 5: Low sample size -> INCREASE_OBSERVATION
            if exp.total_executions < 3:
                return ExperienceRecommendation(
                    action_id=action_id,
                    recommendation_type=RecommendationType.INCREASE_OBSERVATION,
                    confidence=ExperienceConfidence.LOW,
                    reason=(
                        f"Action '{action_id}' has low historical sample size "
                        f"({exp.total_executions} runs)."
                    ),
                    supporting_execution_count=exp.total_executions,
                    generated_at=now_iso,
                )

            # Default Fallback -> RETRY / KEEP_CURRENT_POLICY
            return ExperienceRecommendation(
                action_id=action_id,
                recommendation_type=RecommendationType.KEEP_CURRENT_POLICY,
                confidence=exp.confidence,
                reason=f"Action '{action_id}' operational metrics remain within nominal bounds.",
                supporting_execution_count=exp.total_executions,
                generated_at=now_iso,
            )

    def get_action_experience(self, action_id: str) -> ActionExperience:
        """Returns ActionExperience metrics for action_id."""
        with self._lock:
            return self.store.get_action_experience(action_id)

    def get_recent_outcomes(
        self, action_id: str | None = None, limit: int = 100
    ) -> list[OutcomeRecord]:
        """Returns recent OutcomeRecords."""
        with self._lock:
            return self.store.get_recent_outcomes(action_id=action_id, limit=limit)

    def get_recommendations(self, action_id: str | None = None) -> list[ExperienceRecommendation]:
        """Returns active recommendations generated for actions."""
        with self._lock:
            if action_id is not None:
                rec = self._recommendations.get(action_id)
                return [rec] if rec else []
            return list(self._recommendations.values())

    def get_failure_patterns(self, action_id: str | None = None) -> list[dict[str, Any]]:
        """Returns detected failure pattern records."""
        with self._lock:
            if action_id is not None:
                return [p for p in self._detected_patterns if p.get("action_id") == action_id]
            return list(self._detected_patterns)

    def get_experience_snapshot(self) -> ExperienceStatusSnapshot:
        """Returns an immutable diagnostic snapshot of experience engine metrics."""
        with self._lock:
            all_outcomes = self.store.get_recent_outcomes(limit=10000)
            total = len(all_outcomes)
            succ = sum(1 for o in all_outcomes if o.success)
            fail = sum(1 for o in all_outcomes if not o.success)
            timeouts = sum(1 for o in all_outcomes if o.outcome_type == OutcomeType.TIMED_OUT)
            rollbacks = sum(1 for o in all_outcomes if o.rollback_performed)
            compensations = sum(1 for o in all_outcomes if o.compensation_performed)

            tracked_actions = len({o.action_id for o in all_outcomes})
            last_at = all_outcomes[0].completed_at if all_outcomes else None

            return ExperienceStatusSnapshot(
                total_outcomes=total,
                successful_outcomes=succ,
                failed_outcomes=fail,
                timeout_outcomes=timeouts,
                rollback_outcomes=rollbacks,
                compensation_outcomes=compensations,
                tracked_actions=tracked_actions,
                recommendations_generated=self._recommendations_generated_count,
                failure_patterns_detected=self._failure_patterns_count,
                last_outcome_at=last_at,
            )

    # EventBus Handlers for Stage 12 Integration
    def _on_execution_completed(self, event: Any) -> None:
        rec = OutcomeRecord(
            execution_id=getattr(event, "execution_id", ""),
            action_id=getattr(event, "goal_id", None) or "default_action",
            goal_id=getattr(event, "goal_id", None),
            outcome_type=OutcomeType.SUCCESS,
            success=True,
            completed_at=self.clock.now_iso(),
        )
        self.record_outcome(rec)

    def _on_execution_failed(self, event: Any) -> None:
        rec = OutcomeRecord(
            execution_id=getattr(event, "execution_id", ""),
            action_id=getattr(event, "goal_id", None) or "default_action",
            goal_id=getattr(event, "goal_id", None),
            outcome_type=OutcomeType.FAILURE,
            success=False,
            failure_type=getattr(event, "failure_type", None),
            error=getattr(event, "error", None),
            completed_at=self.clock.now_iso(),
        )
        self.record_outcome(rec)

    def _on_execution_rolled_back(self, event: Any) -> None:
        rec = OutcomeRecord(
            execution_id=getattr(event, "execution_id", ""),
            action_id="default_action",
            outcome_type=OutcomeType.ROLLED_BACK,
            success=False,
            rollback_performed=True,
            error=getattr(event, "reason", None),
            completed_at=self.clock.now_iso(),
        )
        self.record_outcome(rec)

    def _on_execution_compensated(self, event: Any) -> None:
        rec = OutcomeRecord(
            execution_id=getattr(event, "execution_id", ""),
            action_id="default_action",
            outcome_type=OutcomeType.COMPENSATED,
            success=getattr(event, "success", True),
            compensation_performed=True,
            error=getattr(event, "reason", None),
            completed_at=self.clock.now_iso(),
        )
        self.record_outcome(rec)

    def _on_execution_cancelled(self, event: Any) -> None:
        rec = OutcomeRecord(
            execution_id=getattr(event, "execution_id", ""),
            action_id="default_action",
            outcome_type=OutcomeType.CANCELLED,
            success=False,
            error=getattr(event, "reason", None),
            completed_at=self.clock.now_iso(),
        )
        self.record_outcome(rec)

    def _on_execution_timed_out(self, event: Any) -> None:
        rec = OutcomeRecord(
            execution_id=getattr(event, "execution_id", ""),
            action_id="default_action",
            outcome_type=OutcomeType.TIMED_OUT,
            success=False,
            error=f"Timeout after {getattr(event, 'timeout_seconds', 0)}s",
            completed_at=self.clock.now_iso(),
        )
        self.record_outcome(rec)
