from __future__ import annotations

from pathlib import Path

from aura import AURA, AURABootOptions
from aura.cognition import CognitionModule
from aura.cognition.memory_detector import ExplicitMemoryDetector
from aura.config import ConfigurationManager
from aura.events import EventBus
from aura.memory import (
    EpisodicMemory,
    Fact,
    MemoryRetrievalEngine,
    SemanticMemory,
    SQLiteMemoryStore,
    UserPreferencesMemory,
)


def test_semantic_retrieval_cumpleanos_variations(tmp_path: Path) -> None:
    db_file = str(tmp_path / "test_cumple.db")
    store = SQLiteMemoryStore(db_path=db_file)

    bus = EventBus()
    episodic = EpisodicMemory(event_bus=bus, store=store)
    semantic = SemanticMemory(event_bus=bus, store=store)
    prefs = UserPreferencesMemory(event_bus=bus, store=store)

    # Save birthday fact
    semantic.add_fact(
        Fact(
            subject="usuario",
            predicate="cumpleaños",
            object_val="2 de agosto",
            confidence=1.0,
            source="user",
        )
    )
    store.close()

    # Re-open SQLite store (Session 2)
    store2 = SQLiteMemoryStore(db_path=db_file)
    semantic2 = SemanticMemory(event_bus=bus, store=store2)
    retrieval2 = MemoryRetrievalEngine(
        episodic=episodic,
        semantic=semantic2,
        preferences=prefs,
        event_bus=bus,
    )

    queries = [
        "¿Cuál es mi cumpleaños?",
        "¿Cuándo cumplo años?",
        "¿Recuerdas cuándo cumplo años?",
        "¿Qué día cumplo?",
        "Ahora, ¿recuerdas cuantos me cumplí años?",
    ]

    for q in queries:
        res = retrieval2.query(q)
        assert len(res.facts) >= 1, f"Failed to retrieve for query: '{q}'"
        assert res.facts[0].object_val == "2 de agosto", f"Incorrect value for query: '{q}'"

    store2.close()


def test_semantic_retrieval_color_favorito_variations(tmp_path: Path) -> None:
    db_file = str(tmp_path / "test_color.db")
    store = SQLiteMemoryStore(db_path=db_file)

    bus = EventBus()
    episodic = EpisodicMemory(event_bus=bus, store=store)
    semantic = SemanticMemory(event_bus=bus, store=store)
    prefs = UserPreferencesMemory(event_bus=bus, store=store)

    retrieval = MemoryRetrievalEngine(
        episodic=episodic,
        semantic=semantic,
        preferences=prefs,
        event_bus=bus,
    )

    semantic.add_fact(
        Fact(
            subject="usuario",
            predicate="color_favorito",
            object_val="azul",
            confidence=1.0,
            source="user",
        )
    )

    queries = [
        "mi color favorito",
        "qué color me gusta",
        "cuál es mi color preferido",
        "qué color prefiero",
    ]

    for q in queries:
        res = retrieval.query(q)
        assert len(res.facts) >= 1, f"Failed to retrieve for query: '{q}'"
        assert res.facts[0].object_val == "azul"

    store.close()


def test_update_single_valued_fact_removes_duplicates(tmp_path: Path) -> None:
    db_file = str(tmp_path / "test_update.db")
    store = SQLiteMemoryStore(db_path=db_file)

    bus = EventBus()
    semantic = SemanticMemory(event_bus=bus, store=store)

    # 1. Store initial birthday: 8 de agosto
    fact1 = Fact(
        subject="usuario",
        predicate="cumpleaños",
        object_val="8 de agosto",
    )
    semantic.add_fact(fact1)
    assert len(semantic.all_facts()) == 1

    # 2. Update birthday: 2 de agosto
    fact2 = Fact(
        subject="usuario",
        predicate="cumpleaños",
        object_val="2 de agosto",
    )
    semantic.add_fact(fact2)

    # Should only have 1 single updated fact in RAM and SQLite
    all_f = semantic.all_facts()
    assert len(all_f) == 1
    assert all_f[0].object_val == "2 de agosto"

    store.close()

    # Verify SQLite on disk
    store_check = SQLiteMemoryStore(db_path=db_file)
    db_facts = store_check.get_facts(subject="usuario", predicate="cumpleaños")
    assert len(db_facts) == 1
    assert db_facts[0].object_val == "2 de agosto"
    store_check.close()


def test_explicit_memory_detector_with_preamble_and_self_correction() -> None:
    text = (
        "Hola AURA, quiero que recuerdes que mi cumpleaños es el 8 de agosto, "
        "digo no, el 2 de agosto."
    )
    d1 = ExplicitMemoryDetector.detect(text)
    assert d1.detected is True
    assert d1.predicate == "cumpleaños"
    assert d1.object_val == "el 2 de agosto"

    d2 = ExplicitMemoryDetector.detect("Oye AURA, recuerda que mi color favorito es azul")
    assert d2.detected is True
    assert d2.predicate == "color_favorito"
    assert d2.object_val == "azul"


def test_retrieval_to_cognitive_context_format(tmp_path: Path) -> None:
    db_file = str(tmp_path / "test_context.db")

    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)

    # Teach fact
    cog.process_cognitive_cycle(
        "Hola AURA, quiero que recuerdes que mi cumpleaños es el 2 de agosto"
    )

    # Build context for question
    ctx = cog.context_builder.build("¿Cuándo cumplo años?")
    sys_prompt = ctx.to_system_prompt()

    assert "RECUERDOS DE MEMORIA PERSISTENTE DEL USUARIO:" in sys_prompt
    assert "cumpleaños del usuario" in sys_prompt
    assert "2 de agosto" in sys_prompt

    aura.shutdown(wait=True)
