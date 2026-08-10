from __future__ import annotations

from typing import TYPE_CHECKING

from .episodic import EpisodicMemory
from .models import Fact, MemoryQueryResult, Preference
from .preferences import UserPreferencesMemory
from .semantic import SemanticMemory

if TYPE_CHECKING:
    from ..events import EventBus


class MemoryRetrievalEngine:
    """Unified hybrid retrieval engine across Episodic, Semantic and Preferences memory."""

    def __init__(
        self,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        preferences: UserPreferencesMemory,
        event_bus: EventBus | None = None,
    ) -> None:
        self.episodic = episodic
        self.semantic = semantic
        self.preferences = preferences
        self.event_bus = event_bus

    def query(self, search_text: str, limit: int = 5) -> MemoryQueryResult:
        import re

        clean_text = search_text.lower()
        words = [w for w in re.findall(r"\w+", clean_text) if len(w) > 2]

        episodes = self.episodic.search_episodes(search_text, limit=limit)

        all_facts = self.semantic.all_facts()
        matched_facts: list[Fact] = []
        for f in all_facts:
            f_str = f"{f.subject} {f.predicate} {f.object_val}".lower()
            if any(w in f_str for w in words) or len(all_facts) <= 10:
                if f not in matched_facts:
                    matched_facts.append(f)

        all_prefs = self.preferences.all_preferences()
        matched_prefs: list[Preference] = []
        for p in all_prefs:
            p_str = f"{p.key} {p.value}".lower()
            if any(w in p_str for w in words) or len(all_prefs) <= 10:
                if p not in matched_prefs:
                    matched_prefs.append(p)

        result = MemoryQueryResult(
            episodes=episodes[:limit],
            facts=matched_facts[:limit],
            preferences=matched_prefs[:limit],
        )

        if self.event_bus is not None:
            from ..events import MemoryQueried

            total = len(episodes) + len(matched_facts) + len(matched_prefs)
            self.event_bus.publish(
                MemoryQueried(
                    source="MemoryRetrievalEngine",
                    query=search_text,
                    results_count=total,
                )
            )

        return result
