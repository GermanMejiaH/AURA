from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnaphoraResolution:
    """Represents deterministic analysis of anaphoric reference in user input."""

    resolved_entity: str | None = None
    is_ambiguous: bool = False
    candidate_entities: list[str] = field(default_factory=list)
    requires_reference: bool = False


class AnaphoraResolver:
    """Analyzes and resolves conversational references in a deterministic, conservative manner."""

    REFERENCE_TRIGGERS = (
        r"\b(?:cu[aá]l|esa?|eso|este|esta|esto|la|lo|los|las|ella|[eé]l|aqu[eé]lla?|aquello)\b",
    )

    @classmethod
    def analyze(
        cls,
        user_input: str,
        recent_entities: list[str] | None = None,
        active_topic: str | None = None,
        active_entity: str | None = None,
    ) -> AnaphoraResolution:
        if not user_input or not user_input.strip():
            return AnaphoraResolution(requires_reference=False)

        text_clean = user_input.strip().lower()

        # Check if the phrase actually requires a contextual reference
        has_ref_trigger = False
        for pat in cls.REFERENCE_TRIGGERS:
            if re.search(pat, text_clean, re.IGNORECASE):
                has_ref_trigger = True
                break

        if not has_ref_trigger:
            return AnaphoraResolution(requires_reference=False)

        candidates = list(dict.fromkeys(recent_entities)) if recent_entities else []

        # Conservative, deterministic resolution policy:
        if len(candidates) == 1:
            return AnaphoraResolution(
                resolved_entity=candidates[0],
                is_ambiguous=False,
                candidate_entities=candidates,
                requires_reference=True,
            )
        elif len(candidates) > 1:
            # Multiple plausible candidates -> DO NOT pick arbitrarily. Flag ambiguity!
            return AnaphoraResolution(
                resolved_entity=None,
                is_ambiguous=True,
                candidate_entities=candidates,
                requires_reference=True,
            )
        else:
            # 0 candidate entities listed: check active_entity or active_topic fallback
            fallback = active_entity or active_topic
            if fallback:
                return AnaphoraResolution(
                    resolved_entity=fallback,
                    is_ambiguous=False,
                    candidate_entities=[fallback],
                    requires_reference=True,
                )

            return AnaphoraResolution(
                resolved_entity=None,
                is_ambiguous=False,
                candidate_entities=[],
                requires_reference=True,
            )


@dataclass
class ConversationContext:
    """Compiled conversation context selected for a specific cognitive cycle."""

    active_topic: str | None = None
    active_task: str | None = None
    task_detail: str | None = None
    active_entity: str | None = None
    relevant_turns: list[dict[str, str]] = field(default_factory=list)
    anaphora_resolution: AnaphoraResolution | None = None
    recent_tool_results: list[dict[str, Any]] = field(default_factory=list)


class ConversationContextFilter:
    """Filters conversation history deterministically to select top relevant turns (max 8)."""

    DEFAULT_MAX_TURNS: int = 8

    @classmethod
    def filter_turns(
        cls,
        history: list[dict[str, str]],
        current_topic: str | None = None,
        active_task: str | None = None,
        task_detail: str | None = None,
        active_entity: str | None = None,
        anaphora_resolution: AnaphoraResolution | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> list[dict[str, str]]:
        """Selects at most max_turns (<=8) relevant turns in original chronological order."""
        if not history:
            return []

        limit = min(max_turns, cls.DEFAULT_MAX_TURNS)
        total_turns = len(history)

        # Target terms for relevance matching
        targets: set[str] = set()
        if active_entity:
            targets.add(active_entity.strip().lower())
        if current_topic:
            targets.add(current_topic.strip().lower())
        if active_task:
            targets.add(active_task.strip().lower())
        if task_detail:
            targets.add(task_detail.strip().lower())

        if (
            anaphora_resolution
            and not anaphora_resolution.is_ambiguous
            and anaphora_resolution.resolved_entity
        ):
            targets.add(anaphora_resolution.resolved_entity.strip().lower())

        scored_turns: list[tuple[int, float, dict[str, str]]] = []

        for idx, turn in enumerate(history):
            content = turn.get("content", "").lower()

            # Recency score (normalized 0.1 to 1.0)
            recency_score = (idx + 1) / total_turns

            # Contextual relevance score
            relevance_score = 0.0
            for tgt in targets:
                if tgt and tgt in content:
                    relevance_score += 1.0
                elif tgt:
                    # Check individual words > 3 chars
                    words = [w for w in tgt.split() if len(w) > 3]
                    for w in words:
                        if w in content:
                            relevance_score += 0.5

            # Combine recency and relevance
            total_score = (recency_score * 2.0) + relevance_score
            scored_turns.append((idx, total_score, turn))

        # Select top scored turns up to `limit`
        scored_turns.sort(key=lambda x: x[1], reverse=True)
        top_selected = scored_turns[:limit]

        # Re-sort by original index to guarantee original chronological order
        top_selected.sort(key=lambda x: x[0])

        return [turn for _, _, turn in top_selected]
