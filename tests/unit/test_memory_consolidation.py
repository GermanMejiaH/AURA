from __future__ import annotations

from aura.cognition import WorkingMemory
from aura.events import EventBus, MemoryConsolidated, MemoryQueried
from aura.memory import (
    EpisodicMemory,
    MemoryConsolidator,
    MemoryRetrievalEngine,
    SemanticMemory,
    UserPreferencesMemory,
)


def test_memory_consolidation_and_retrieval():
    bus = EventBus()
    episodic = EpisodicMemory(event_bus=bus)
    semantic = SemanticMemory(event_bus=bus)
    prefs = UserPreferencesMemory(event_bus=bus)

    consolidator = MemoryConsolidator(episodic=episodic, semantic=semantic, event_bus=bus)
    retrieval = MemoryRetrievalEngine(
        episodic=episodic,
        semantic=semantic,
        preferences=prefs,
        event_bus=bus,
    )

    wm = WorkingMemory()
    wm.add_conversation_turn("user", "Recordatorio de reunión mañana")

    cons_events: list[MemoryConsolidated] = []
    query_events: list[MemoryQueried] = []
    bus.subscribe("MemoryConsolidated", lambda e: cons_events.append(e))
    bus.subscribe("MemoryQueried", lambda e: query_events.append(e))

    res_count = consolidator.consolidate_working_memory(wm)
    assert res_count == 1
    assert len(cons_events) == 1
    assert episodic.count() == 1

    query_res = retrieval.query("reunión")
    assert len(query_res.episodes) == 1
    assert len(query_events) == 1
