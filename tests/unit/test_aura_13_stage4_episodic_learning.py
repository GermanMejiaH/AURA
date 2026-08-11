from __future__ import annotations

import json

import pytest

from aura.autonomy.history import AgentExecutionHistoryStore
from aura.cognition.context import CognitiveContext
from aura.cognition.reflection import ReflectionSeverity, ReflectionSummary
from aura.cognition.verification import VerificationResult, VerificationStatus
from aura.memory.episodic import EpisodicMemory, EpisodicMemoryConsolidator
from aura.memory.models import Episode
from aura.memory.retrieval import MemoryRetriever
from aura.memory.store import SQLiteMemoryStore


@pytest.fixture
def memory_store(tmp_path) -> SQLiteMemoryStore:
    db_file = tmp_path / "test_aura_stage4.db"
    return SQLiteMemoryStore(db_path=str(db_file))


@pytest.fixture
def episodic_memory(memory_store) -> EpisodicMemory:
    return EpisodicMemory(store=memory_store)


@pytest.fixture
def history_store(memory_store) -> AgentExecutionHistoryStore:
    return AgentExecutionHistoryStore(store=memory_store)


@pytest.fixture
def consolidator(episodic_memory, history_store, memory_store) -> EpisodicMemoryConsolidator:
    return EpisodicMemoryConsolidator(
        episodic_memory=episodic_memory,
        history_store=history_store,
        store=memory_store,
    )


def make_ver(
    status: VerificationStatus = VerificationStatus.SUCCESS,
    confidence: float = 1.0,
    observations: str = "Execution verified",
    suggested_action: str = "CONTINUE",
) -> VerificationResult:
    return VerificationResult(
        status=status,
        confidence=confidence,
        observations=observations,
        suggested_action=suggested_action,
    )


def make_ref(
    root_cause: str = "Operational error",
    hypotheses: list[str] | None = None,
    lesson_learned: str = "Retry with backoff",
    recommended_action: str = "RETRY",
    severity: ReflectionSeverity = ReflectionSeverity.WARNING,
    observations: str = "Observed error",
    confidence: float = 0.9,
) -> ReflectionSummary:
    return ReflectionSummary(
        severity=severity,
        root_cause=root_cause,
        hypotheses=hypotheses or ["Hypothesis A"],
        observations=observations,
        lesson_learned=lesson_learned,
        recommended_action=recommended_action,
        confidence=confidence,
    )


def test_1_episode_created_with_verification_result(consolidator):
    """Test 1: Episode is correctly created containing VerificationResult metadata."""
    ver = make_ver(
        status=VerificationStatus.SUCCESS,
        confidence=0.95,
        observations="Tool executed cleanly and expected file was created",
    )
    ep = consolidator.consolidate_plan(plan_id="plan_ver_101", verification=ver)
    assert ep is not None
    details = json.loads(ep.details)
    assert details.get("verification_status") == "SUCCESS"
    assert details.get("verification_confidence") == 0.95


def test_2_episode_created_with_reflection_summary(consolidator):
    """Test 2: Episode is correctly created containing ReflectionSummary metadata."""
    ref = make_ref(
        root_cause="Operational failure: network timeout",
        hypotheses=["Network unreachable", "Remote server busy"],
        lesson_learned="Retry with exponential backoff",
        recommended_action="RETRY",
        severity=ReflectionSeverity.WARNING,
        confidence=0.9,
    )
    ep = consolidator.consolidate_plan(plan_id="plan_ref_102", reflection=ref)
    assert ep is not None
    details = json.loads(ep.details)
    assert details.get("recommended_action") == "RETRY"
    assert details.get("reflection_severity") == "WARNING"


def test_3_enriched_episode_contains_root_cause(consolidator):
    """Test 3: Enriched episode contains root_cause field in metadata."""
    ref = make_ref(
        root_cause="Database connection pool exhausted",
        hypotheses=["Too many active clients"],
        lesson_learned="Increase pool limit or release connections promptly",
        recommended_action="REPLAN",
        severity=ReflectionSeverity.CRITICAL,
    )
    ep = consolidator.consolidate_plan(plan_id="plan_rc_103", reflection=ref)
    details = json.loads(ep.details)
    assert details.get("root_cause") == "Database connection pool exhausted"


def test_4_enriched_episode_contains_hypotheses(consolidator):
    """Test 4: Enriched episode contains hypotheses list in metadata."""
    ref = make_ref(
        root_cause="File not found",
        hypotheses=["Incorrect file path", "Directory permission denied"],
        lesson_learned="Verify path existence prior to read operation",
        recommended_action="CONTINUE",
    )
    ep = consolidator.consolidate_plan(plan_id="plan_hyp_104", reflection=ref)
    details = json.loads(ep.details)
    assert details.get("hypotheses") == ["Incorrect file path", "Directory permission denied"]


def test_5_enriched_episode_contains_lesson_learned(consolidator):
    """Test 5: Enriched episode contains lesson_learned field in metadata and summary."""
    ref = make_ref(
        root_cause="API key missing",
        lesson_learned="Ensure API key environment variable is populated",
        recommended_action="ABORT",
    )
    ep = consolidator.consolidate_plan(plan_id="plan_les_105", reflection=ref)
    details = json.loads(ep.details)
    assert details.get("lesson_learned") == "Ensure API key environment variable is populated"
    assert "Lección aprendida: Ensure API key environment variable" in ep.summary


def test_6_enriched_episode_contains_recommended_action(consolidator):
    """Test 6: Enriched episode contains recommended_action field in metadata."""
    ref = make_ref(
        root_cause="Transient delay",
        recommended_action="RETRY",
    )
    ep = consolidator.consolidate_plan(plan_id="plan_rec_106", reflection=ref)
    details = json.loads(ep.details)
    assert details.get("recommended_action") == "RETRY"


def test_7_legacy_episodes_remain_compatible(memory_store, episodic_memory):
    """Test 7: Legacy episodes without reflection or verification metadata remain valid."""
    legacy_details = json.dumps(
        {
            "plan_id": "legacy_plan_001",
            "goal_description": "Legacy plan execution",
            "outcome": "SUCCESS",
            "tools_used": ["calculator"],
        }
    )
    legacy_ep = Episode(
        id="ep_plan_legacy_plan_001",
        summary="Legacy execution completed",
        details=legacy_details,
        tags=["agent_plan", "success"],
    )
    episodic_memory.record_episode(legacy_ep)

    retriever = MemoryRetriever(store=memory_store)
    results = retriever.search(query="calculator")
    assert len(results) >= 1
    matched = results[0]
    assert matched.episode.id == "ep_plan_legacy_plan_001"
    details = json.loads(matched.episode.details)
    assert "root_cause" not in details


def test_8_memory_retriever_retrieves_enriched_episodes(memory_store, consolidator):
    """Test 8: MemoryRetriever can query and retrieve enriched episodes."""
    ref = make_ref(
        root_cause="Timeout while reaching server_v2 endpoint",
        lesson_learned="Use server_v1 fallback endpoint when server_v2 times out",
        recommended_action="RETRY",
    )
    consolidator.consolidate_plan(plan_id="plan_net_200", reflection=ref)

    retriever = MemoryRetriever(store=memory_store)
    results = retriever.search(query="server_v2 timeout")
    assert len(results) >= 1
    top_ep = results[0].episode
    details = json.loads(top_ep.details)
    assert "server_v2" in details.get("root_cause", "")


def test_9_scoring_remains_deterministic(memory_store, consolidator):
    """Test 9: Scoring remains strictly deterministic across multiple search invocations."""
    ref = make_ref(
        root_cause="Storage quota exceeded",
        lesson_learned="Purge temporary files before large write",
        recommended_action="REPLAN",
    )
    consolidator.consolidate_plan(plan_id="plan_det_300", reflection=ref)

    retriever = MemoryRetriever(store=memory_store)
    res1 = retriever.search(query="storage purge")
    res2 = retriever.search(query="storage purge")

    assert len(res1) == len(res2)
    for r1, r2 in zip(res1, res2, strict=False):
        assert r1.episode.id == r2.episode.id
        assert r1.score == r2.score
        assert r1.explanation == r2.explanation


def test_10_cognitive_context_builder_incorporates_learned_lesson():
    """Test 10: CognitiveContextBuilder formats retrieved lessons into system prompt."""
    ep_details = json.dumps(
        {
            "plan_id": "plan_cc_400",
            "lesson_learned": "Apply backoff delay before retrying API request",
        }
    )
    ep = Episode(
        id="ep_plan_plan_cc_400",
        summary="Plan for API request",
        details=ep_details,
    )
    ctx = CognitiveContext(
        system_instruction="Instruction",
        user_input="Retry API call",
        relevant_episodes=[ep],
    )
    prompt = ctx.to_system_prompt()
    assert "[EXPERIENCIAS EPISÓDICAS PASADAS RELEVANTES]:" in prompt
    assert "Lección aprendida: Apply backoff delay before retrying API request" in prompt


def test_11_no_duplicate_episodes_generated(consolidator):
    """Test 11: Idempotency is preserved; duplicate consolidation returns existing episode."""
    ver = make_ver(status=VerificationStatus.SUCCESS)
    ep1 = consolidator.consolidate_plan(plan_id="plan_idempotent_500", verification=ver)
    ep2 = consolidator.consolidate_plan(plan_id="plan_idempotent_500", verification=ver)
    assert ep1 is not None and ep2 is not None
    assert ep1.id == ep2.id


def test_12_sensitive_metadata_sanitized(consolidator):
    """Test 12: Sensitive tokens in reflection root_cause/hypotheses/lesson are sanitized."""
    ref = make_ref(
        root_cause="Failed with secret key sk-1234567890",
        hypotheses=["Authorization Bearer secret_token_xyz"],
        lesson_learned="Store api_key in environment variables",
        recommended_action="ABORT",
    )
    ep = consolidator.consolidate_plan(plan_id="plan_sec_600", reflection=ref)
    details = json.loads(ep.details)
    assert "sk-1234567890" not in details["root_cause"]
    assert "[REDACTED_SECRET]" in details["root_cause"]
    assert "secret_token_xyz" not in str(details["hypotheses"])


def test_13_missing_verification_or_reflection_does_not_break_consolidator(consolidator):
    """Test 13: Consolidation without verification/reflection parameters succeeds cleanly."""
    ep = consolidator.consolidate_plan(plan_id="plan_clean_700")
    assert ep is not None
    details = json.loads(ep.details)
    assert "verification_status" not in details
    assert "root_cause" not in details


def test_14_successful_executions_consolidated_without_invented_lessons(consolidator):
    """Test 14: Successful executions consolidate clean metadata without fake lessons."""
    ver = make_ver(
        status=VerificationStatus.SUCCESS,
        observations="Action completed cleanly",
    )
    ref = make_ref(
        root_cause="",
        lesson_learned="",
        recommended_action="CONTINUE",
        severity=ReflectionSeverity.INFO,
    )
    ep = consolidator.consolidate_plan(plan_id="plan_success_800", verification=ver, reflection=ref)
    details = json.loads(ep.details)
    assert details.get("verification_status") == "SUCCESS"
    assert details.get("lesson_learned") == ""
    assert "Lección aprendida:" not in ep.summary


def test_15_transient_failures_preserve_diagnosis_and_recommended_action(consolidator):
    """Test 15: Transient failures preserve diagnostic details and recommended action RETRY."""
    ver = make_ver(
        status=VerificationStatus.TRANSIENT_FAILURE,
        observations="HTTP 503 Service Unavailable",
    )
    ref = make_ref(
        root_cause="Transient server overload",
        lesson_learned="Wait 2 seconds before retry",
        recommended_action="RETRY",
        severity=ReflectionSeverity.WARNING,
    )
    ep = consolidator.consolidate_plan(
        plan_id="plan_transient_900", verification=ver, reflection=ref
    )
    details = json.loads(ep.details)
    assert details.get("verification_status") == "TRANSIENT_FAILURE"
    assert details.get("recommended_action") == "RETRY"
    assert details.get("reflection_severity") == "WARNING"


def test_16_fatal_failures_preserve_diagnosis_and_severity(consolidator):
    """Test 16: Fatal failures preserve root cause diagnosis and CRITICAL/HIGH severity."""
    ver = make_ver(
        status=VerificationStatus.FATAL_FAILURE,
        observations="Permission denied (HTTP 403 Forbidden)",
    )
    ref = make_ref(
        root_cause="Insufficient authorization credentials",
        lesson_learned="Request elevated permissions before execution",
        recommended_action="ABORT",
        severity=ReflectionSeverity.CRITICAL,
    )
    ep = consolidator.consolidate_plan(plan_id="plan_fatal_999", verification=ver, reflection=ref)
    details = json.loads(ep.details)
    assert details.get("verification_status") == "FATAL_FAILURE"
    assert details.get("root_cause") == "Insufficient authorization credentials"
    assert details.get("reflection_severity") == "CRITICAL"
