from __future__ import annotations

import json
from typing import Any

from ...memory.retrieval import MemoryResult, MemoryRetriever
from .models import GoalModel, RiskLevel, SimulationOutcome, StrategyCandidate


class OutcomeSimulator:
    """Evaluates candidate strategies deterministically using historical episodic evidence."""

    def __init__(self, memory_retriever: MemoryRetriever) -> None:
        self.retriever = memory_retriever

    def _determine_risk_level(self, risk_score: float) -> RiskLevel:
        """Derives RiskLevel deterministically from risk_score."""
        if risk_score < 0.25:
            return RiskLevel.LOW
        elif risk_score < 0.50:
            return RiskLevel.MEDIUM
        elif risk_score < 0.75:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    def simulate(
        self,
        strategy: StrategyCandidate,
        goal: GoalModel,
    ) -> SimulationOutcome:
        """Simulates historical risks and estimates success rate for a candidate strategy."""
        # 1. Baseline metrics
        success_rate = 0.80
        risk_score = 0.20

        # 2. Adjust for estimated_complexity (1.0 to 5.0)
        complexity_risk_adj = (strategy.estimated_complexity - 1.0) * 0.025
        risk_score += complexity_risk_adj

        # 3. Retrieve historical evidence for strategy required_tools and goal description
        query = f"{goal.description} {' '.join(strategy.required_tools)}"
        results: list[MemoryResult] = []
        try:
            results = self.retriever.search(
                query=query.strip(),
                tools=strategy.required_tools or None,
                limit=10,
            )
        except Exception:
            results = []

        matched_lessons: list[str] = []
        potential_bottlenecks: list[str] = []
        explanation_parts: list[str] = []

        failed_count = 0
        matching_root_causes = 0
        matching_lessons_count = 0

        # 4. Analyze retrieved historical episodes
        for res in results:
            ep = res.episode
            details: dict[str, Any] = {}
            if ep.details:
                try:
                    details = json.loads(ep.details)
                except Exception:
                    details = {}

            ep_tools = [str(t).lower() for t in details.get("tools_used", [])]
            tools_intersect = set(t.lower() for t in strategy.required_tools).intersection(ep_tools)
            outcome = str(details.get("outcome", "")).upper()
            ver_status = str(details.get("verification_status", "")).upper()

            # Lesson learned match
            lesson = details.get("lesson_learned")
            if lesson and isinstance(lesson, str) and lesson.strip():
                clean_lesson = lesson.strip()
                if clean_lesson not in matched_lessons:
                    matched_lessons.append(clean_lesson)
                    matching_lessons_count += 1

            # Root cause match
            root_cause = details.get("root_cause")
            if root_cause and isinstance(root_cause, str) and root_cause.strip():
                clean_cause = root_cause.strip()
                if clean_cause not in potential_bottlenecks:
                    potential_bottlenecks.append(clean_cause)
                    matching_root_causes += 1

            # Failure penalty
            if outcome == "FAILED" or ver_status in ("FATAL_FAILURE", "TRANSIENT_FAILURE"):
                failed_count += 1
                if tools_intersect:
                    for t in sorted(list(tools_intersect)):
                        btnk = f"Tool '{t}' has historical failures ({ver_status or outcome})"
                        if btnk not in potential_bottlenecks:
                            potential_bottlenecks.append(btnk)

        # 5. Apply deterministic scoring adjustments from evidence
        if matching_lessons_count > 0:
            success_rate -= 0.10 * matching_lessons_count
            risk_score += 0.10 * matching_lessons_count
            explanation_parts.append(
                f"Matches {matching_lessons_count} historical learned lesson(s)"
            )

        if matching_root_causes > 0:
            success_rate -= 0.15 * matching_root_causes
            risk_score += 0.15 * matching_root_causes
            explanation_parts.append(
                f"Matches {matching_root_causes} historical root cause bottleneck(s)"
            )

        if failed_count > 0:
            failed_penalty = min(0.20, failed_count * 0.05)
            success_rate -= failed_penalty
            risk_score += failed_penalty
            explanation_parts.append(
                f"Recorded {failed_count} historical failed execution trace(s)"
            )

        # 6. Evaluate GoalModel constraints & risk_tolerance
        if goal.constraints and strategy.required_tools:
            for c in goal.constraints:
                c_lower = c.lower()
                if "no_cmd" in c_lower or "no_exec" in c_lower or "read_only" in c_lower:
                    if any(t.lower() in ("cmd", "exec", "write") for t in strategy.required_tools):
                        risk_score += 0.20
                        success_rate -= 0.20
                        btnk = f"Strategy tools violate constraint: '{c}'"
                        if btnk not in potential_bottlenecks:
                            potential_bottlenecks.append(btnk)
                        explanation_parts.append(f"Constraint violation: {c}")

        # Risk tolerance adjustment
        if goal.risk_tolerance == RiskLevel.LOW:
            if risk_score > 0.30:
                risk_score += 0.10
                success_rate -= 0.10
                explanation_parts.append("Goal specifies LOW risk tolerance")
        elif goal.risk_tolerance == RiskLevel.HIGH:
            risk_score = max(0.0, risk_score - 0.05)
            explanation_parts.append("Goal specifies HIGH risk tolerance")

        # 7. Clamp values strictly within 0.0 <= val <= 1.0
        success_rate = round(max(0.0, min(1.0, success_rate)), 4)
        risk_score = round(max(0.0, min(1.0, risk_score)), 4)

        risk_lvl = self._determine_risk_level(risk_score)

        if not explanation_parts:
            explanation_parts.append("Baseline simulation with clean historical record")

        exp_str = f"Strategy '{strategy.name}': " + "; ".join(explanation_parts) + "."

        return SimulationOutcome(
            strategy_id=strategy.strategy_id,
            estimated_success_rate=success_rate,
            risk_score=risk_score,
            risk_level=risk_lvl,
            potential_bottlenecks=potential_bottlenecks,
            matched_lessons=matched_lessons,
            explanation=exp_str,
        )
