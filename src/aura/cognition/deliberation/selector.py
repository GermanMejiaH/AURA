from __future__ import annotations

from .models import GoalModel, RiskLevel, SimulationOutcome, StrategyCandidate, StrategySelection


class StrategySelector:
    """Deterministic selection engine ranking candidate strategies against GoalModel criteria."""

    SUCCESS_WEIGHT: float = 0.60
    RISK_WEIGHT: float = 0.30
    COMPLEXITY_WEIGHT: float = 0.10

    def select(
        self,
        goal: GoalModel,
        candidates: list[StrategyCandidate],
        simulations: list[SimulationOutcome],
    ) -> StrategySelection:
        """Selects the optimal viable StrategyCandidate based on deterministic scoring."""
        # 1. Input validations
        if not candidates:
            raise ValueError("candidates list cannot be empty")
        if not simulations:
            raise ValueError("simulations list cannot be empty")

        cand_ids = [c.strategy_id for c in candidates]
        if len(cand_ids) != len(set(cand_ids)):
            raise ValueError("Duplicate strategy_id found in candidates list")

        sim_ids = [s.strategy_id for s in simulations]
        if len(sim_ids) != len(set(sim_ids)):
            raise ValueError("Duplicate strategy_id found in simulations list")

        sim_map: dict[str, SimulationOutcome] = {s.strategy_id: s for s in simulations}
        if set(cand_ids) != set(sim_ids):
            raise ValueError("Mismatch between candidates and simulations strategy_ids")

        rejection_reasons: dict[str, str] = {}
        viable_evaluations: list[tuple[StrategyCandidate, SimulationOutcome, float]] = []

        # 2. Evaluate each candidate
        for cand in candidates:
            sim = sim_map[cand.strategy_id]
            rejected = False

            # Check constraints alignment
            if goal.constraints:
                for constraint in goal.constraints:
                    c_lower = constraint.lower()
                    if "no_cmd" in c_lower or "no_exec" in c_lower:
                        if any(
                            t.lower() in ("cmd", "exec", "exec_cmd") for t in cand.required_tools
                        ):
                            rejection_reasons[cand.strategy_id] = (
                                f"Violates constraint '{constraint}'"
                            )
                            rejected = True
                            break
                    elif "read_only" in c_lower:
                        write_keywords = ("write", "delete", "update", "modify", "exec", "cmd")
                        if any(
                            any(w in t.lower() for w in write_keywords) for t in cand.required_tools
                        ):
                            rejection_reasons[cand.strategy_id] = (
                                f"Violates constraint '{constraint}'"
                            )
                            rejected = True
                            break

            if rejected:
                continue

            # Check risk tolerance alignment
            if goal.risk_tolerance == RiskLevel.LOW:
                if sim.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                    rejection_reasons[cand.strategy_id] = (
                        f"Risk level {sim.risk_level.value} exceeds goal risk tolerance LOW"
                    )
                    continue

            # Compute score
            norm_complexity = (cand.estimated_complexity - 1.0) / 4.0
            score = (
                (self.SUCCESS_WEIGHT * sim.estimated_success_rate)
                - (self.RISK_WEIGHT * sim.risk_score)
                - (self.COMPLEXITY_WEIGHT * norm_complexity)
            )

            # Risk tolerance score adjustments
            if goal.risk_tolerance == RiskLevel.LOW:
                score -= 0.10
            elif goal.risk_tolerance == RiskLevel.HIGH:
                score += 0.05

            viable_evaluations.append((cand, sim, score))

        # 3. Handle zero viable strategies
        if not viable_evaluations:
            rejection_details = "; ".join(
                f"'{sid}': {reason}" for sid, reason in sorted(rejection_reasons.items())
            )
            raise ValueError(
                f"No viable strategy found for goal '{goal.goal_id}'. "
                f"Rejections: {rejection_details}"
            )

        # 4. Deterministic tie-breaking selection
        best_cand, best_sim, best_score = self._select_best(viable_evaluations)

        # 5. Build comparison summary
        summary_lines = [
            (
                f"Selected strategy '{best_cand.strategy_id}' ({best_cand.name}) "
                f"with score={best_score:.4f}."
            ),
            (
                f"Metrics: SuccessRate={best_sim.estimated_success_rate:.2f}, "
                f"RiskScore={best_sim.risk_score:.2f}, "
                f"Complexity={best_cand.estimated_complexity:.1f}."
            ),
        ]
        for sid, reason in sorted(rejection_reasons.items()):
            summary_lines.append(f"Strategy '{sid}' rejected: {reason}.")

        return StrategySelection(
            goal_id=goal.goal_id,
            chosen_strategy=best_cand,
            chosen_simulation=best_sim,
            all_candidates=list(candidates),
            comparison_summary="\n".join(summary_lines),
            rejection_reasons=rejection_reasons,
        )

    def _select_best(
        self,
        evaluations: list[tuple[StrategyCandidate, SimulationOutcome, float]],
    ) -> tuple[StrategyCandidate, SimulationOutcome, float]:
        """Performs deterministic tie-breaking selection across viable candidates."""
        best = evaluations[0]
        for current in evaluations[1:]:
            if self._is_better(current, best):
                best = current
        return best

    def _is_better(
        self,
        a: tuple[StrategyCandidate, SimulationOutcome, float],
        b: tuple[StrategyCandidate, SimulationOutcome, float],
    ) -> bool:
        """Determines if candidate A is strictly preferred over candidate B."""
        cand_a, sim_a, score_a = a
        cand_b, sim_b, score_b = b

        if abs(score_a - score_b) > 1e-6:
            return score_a > score_b
        if abs(sim_a.estimated_success_rate - sim_b.estimated_success_rate) > 1e-6:
            return sim_a.estimated_success_rate > sim_b.estimated_success_rate
        if abs(sim_a.risk_score - sim_b.risk_score) > 1e-6:
            return sim_a.risk_score < sim_b.risk_score
        if abs(cand_a.estimated_complexity - cand_b.estimated_complexity) > 1e-6:
            return cand_a.estimated_complexity < cand_b.estimated_complexity
        return cand_a.strategy_id < cand_b.strategy_id
