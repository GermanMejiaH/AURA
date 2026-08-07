from __future__ import annotations

from typing import TYPE_CHECKING

from .episodic import EpisodicMemory
from .models import MemoryQueryResult
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
        episodes = self.episodic.search_episodes(search_text, limit=limit)
        facts = self.semantic.query_facts(subject=search_text)
        prefs = [
            p
            for p in self.preferences.all_preferences()
            if search_text.lower() in p.key.lower()
        ]

        result = MemoryQueryResult(episodes=episodes, facts=facts, preferences=prefs)

        if self.event_bus is not None:
            from ..events import MemoryQueried

            total = len(episodes) + len(facts) + len(prefs)
            self.event_bus.publish(
                MemoryQueried(
                    source="MemoryRetrievalEngine",
                    query=search_text,
                    results_count=total,
                )
            )

        return result
