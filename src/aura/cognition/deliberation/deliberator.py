from __future__ import annotations

import hashlib

from .models import GoalModel, StrategyCandidate


class DeliberationEngine:
    """Deterministic, side-effect free deliberation engine generating strategic candidates."""

    MAX_CANDIDATES = 3

    def deliberate(
        self,
        goal: GoalModel,
        available_tools: list[str] | None = None,
    ) -> list[StrategyCandidate]:
        """Generates up to 3 deterministic strategic candidates to achieve the goal."""
        tools = sorted(list(set(available_tools))) if available_tools else []
        candidates: list[StrategyCandidate] = []

        desc = goal.description.strip()
        goal_slug = hashlib.md5(f"{goal.goal_id}_{desc}".encode()).hexdigest()[:8]

        # Candidate 1: Direct Execution Strategy
        s1_tools = [
            t
            for t in tools
            if any(k in t.lower() for k in ("exec", "run", "calc", "cmd", "write", "search"))
        ]
        if not s1_tools and tools:
            s1_tools = [tools[0]]

        candidates.append(
            StrategyCandidate(
                strategy_id=f"strat_{goal_slug}_dir",
                name="Direct Execution Strategy",
                description=f"Direct sequential execution for goal: '{desc}'",
                steps_outline=[
                    f"Analyze objective: {desc}",
                    "Execute primary direct action",
                    "Confirm completion",
                ],
                required_tools=s1_tools,
                estimated_complexity=1.0,
            )
        )

        # Candidate 2: Iterative Verification Strategy
        s2_tools = list(tools)
        candidates.append(
            StrategyCandidate(
                strategy_id=f"strat_{goal_slug}_ver",
                name="Iterative Verification Strategy",
                description=(
                    f"Multi-phase cautious execution with intermediate verifications for: '{desc}'"
                ),
                steps_outline=[
                    "Validate constraints and preconditions",
                    "Execute action in controlled stages",
                    "Verify intermediate step outcomes",
                    "Finalize and log result",
                ],
                required_tools=s2_tools,
                estimated_complexity=2.5,
            )
        )

        # Candidate 3: Conservative Fallback Strategy
        s3_tools = [
            t
            for t in tools
            if any(k in t.lower() for k in ("read", "check", "get", "inspect", "info"))
        ]
        if not s3_tools and tools:
            s3_tools = [tools[-1]]

        candidates.append(
            StrategyCandidate(
                strategy_id=f"strat_{goal_slug}_cnsv",
                name="Conservative Fallback Strategy",
                description=f"Low-risk cautious strategy minimizing side effects for: '{desc}'",
                steps_outline=[
                    "Inspect state and verify safety rules",
                    "Execute minimal required baseline action",
                    "Report outcome and maintain safe state",
                ],
                required_tools=s3_tools,
                estimated_complexity=1.5,
            )
        )

        return candidates[: self.MAX_CANDIDATES]
