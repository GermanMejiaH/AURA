from __future__ import annotations

from typing import TYPE_CHECKING

from .episodic import EpisodicMemory
from .models import Episode
from .semantic import SemanticMemory

if TYPE_CHECKING:
    from ..cognition import WorkingMemory
    from ..events import EventBus


class MemoryConsolidator:
    """Consolidates short-term WorkingMemory items into long-term Episodic/Semantic memory."""

    def __init__(
        self,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        event_bus: EventBus | None = None,
    ) -> None:
        self.episodic = episodic
        self.semantic = semantic
        self.event_bus = event_bus

    def consolidate_working_memory(self, working_memory: WorkingMemory) -> int:
        turns = working_memory.get_recent_conversation(limit=10)
        if not turns:
            return 0

        # Summarize turns into an Episode
        summary_text = f"Conversación reciente ({len(turns)} turnos): {turns[0].get('content', '')}"
        episode = Episode(summary=summary_text, details=str(turns))
        self.episodic.record_episode(episode)

        if self.event_bus is not None:
            from ..events import MemoryConsolidated

            self.event_bus.publish(
                MemoryConsolidated(
                    source="MemoryConsolidator",
                    episodes_consolidated=1,
                    facts_extracted=0,
                )
            )

        return 1
