from __future__ import annotations

from aura.events import EpisodeRecorded, EventBus, FactLearned
from aura.memory import Episode, EpisodicMemory, Fact, SemanticMemory


def test_episodic_memory_record_and_search():
    bus = EventBus()
    episodic = EpisodicMemory(event_bus=bus)

    events: list[EpisodeRecorded] = []
    bus.subscribe("EpisodeRecorded", lambda e: events.append(e))

    ep1 = Episode(summary="Usuario preguntó por el clima", details="Santiago de Chile")
    ep2 = Episode(summary="Usuario configuró la alarma", details="7:00 AM")

    episodic.record_episode(ep1)
    episodic.record_episode(ep2)

    assert episodic.count() == 2
    assert len(events) == 2

    search_res = episodic.search_episodes("clima")
    assert len(search_res) == 1
    assert search_res[0].summary == "Usuario preguntó por el clima"


def test_semantic_memory_facts():
    bus = EventBus()
    semantic = SemanticMemory(event_bus=bus)

    events: list[FactLearned] = []
    bus.subscribe("FactLearned", lambda e: events.append(e))

    fact1 = Fact(subject="Andres", predicate="preferencia_idioma", object_val="es")
    semantic.add_fact(fact1)

    assert semantic.count() == 1
    assert len(events) == 1
    assert events[0].subject == "Andres"

    queried = semantic.query_facts(subject="Andres")
    assert len(queried) == 1
    assert queried[0].object_val == "es"
