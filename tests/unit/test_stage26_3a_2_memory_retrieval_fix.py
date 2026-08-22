"""Unit tests for Stage 26.3A.2 Memory Retrieval Fix & Open Query Recall."""

import pytest

from aura.cognition.context import CognitiveContextBuilder
from aura.container import DependencyContainer
from aura.events import EventBus
from aura.memory.models import Fact
from aura.memory.module import MemoryModule
from aura.memory.preferences import UserPreferencesMemory
from aura.memory.retrieval import MemoryRetrievalEngine
from aura.memory.semantic import SemanticMemory
from aura.memory.store import SQLiteMemoryStore


@pytest.fixture
def in_memory_store() -> SQLiteMemoryStore:
    return SQLiteMemoryStore(db_path=":memory:")


@pytest.fixture
def memory_components(in_memory_store: SQLiteMemoryStore):
    semantic = SemanticMemory(store=in_memory_store)
    preferences = UserPreferencesMemory(store=in_memory_store)
    episodic = MemoryModule(store=in_memory_store).episodic
    engine = MemoryRetrievalEngine(
        episodic=episodic,
        semantic=semantic,
        preferences=preferences,
    )
    return semantic, preferences, engine


def test_open_query_recalls_name(memory_components) -> None:
    semantic, preferences, engine = memory_components

    semantic.add_fact(
        Fact(subject="usuario", predicate="nombre", object_val="Andrés", source="user")
    )
    preferences.set_preference("nombre", "Andrés")

    result = engine.query("¿Qué recuerdas de mí?")
    assert len(result.facts) >= 1
    assert result.facts[0].predicate == "nombre"
    assert result.facts[0].object_val == "Andrés"

    pref_result = engine.query("¿Qué sabes de mí?")
    assert len(pref_result.preferences) >= 1
    assert pref_result.preferences[0].value == "Andrés"


def test_open_query_recalls_studies(memory_components) -> None:
    semantic, _preferences, engine = memory_components

    semantic.add_fact(
        Fact(
            subject="usuario",
            predicate="actividad",
            object_val="estudiando ingeniería software",
            source="user",
        )
    )

    result = engine.query("¿Qué sabes sobre mí?")
    assert len(result.facts) >= 1
    assert result.facts[0].predicate == "actividad"
    assert result.facts[0].object_val == "estudiando ingeniería software"


def test_open_query_recalls_multiple_facts(memory_components) -> None:
    semantic, preferences, engine = memory_components

    f1 = Fact(subject="usuario", predicate="nombre", object_val="Andrés", source="user")
    f2 = Fact(
        subject="usuario",
        predicate="actividad",
        object_val="estudiando ingeniería software",
        source="user",
    )
    semantic.add_fact(f1)
    semantic.add_fact(f2)
    preferences.set_preference("nombre", "Andrés")
    preferences.set_preference("actividad", "estudiando ingeniería software")

    open_queries = [
        "¿Quién soy?",
        "háblame de mí",
        "¿qué conoces de mí?",
        "¿Qué recuerdas de mí?",
    ]

    for q in open_queries:
        res = engine.query(q)
        assert len(res.facts) >= 2, f"Failed for query '{q}'"
        predicates = {f.predicate for f in res.facts}
        assert "nombre" in predicates, f"Missing 'nombre' for query '{q}'"
        assert "actividad" in predicates, f"Missing 'actividad' for query '{q}'"


def test_predicate_queries_still_work(memory_components) -> None:
    semantic, _preferences, engine = memory_components

    f1 = Fact(subject="usuario", predicate="nombre", object_val="Andrés", source="user")
    f2 = Fact(
        subject="usuario",
        predicate="actividad",
        object_val="estudiando ingeniería software",
        source="user",
    )
    semantic.add_fact(f1)
    semantic.add_fact(f2)

    res_name = engine.query("cuál es mi nombre")
    assert len(res_name.facts) >= 1
    assert res_name.facts[0].predicate == "nombre"

    res_study = engine.query("qué estudio")
    assert len(res_study.facts) >= 1
    assert res_study.facts[0].predicate == "actividad"


def test_cognitive_context_builder_populates_memories_on_open_query(
    in_memory_store: SQLiteMemoryStore,
) -> None:
    container = DependencyContainer()
    event_bus = EventBus()

    mem_module = MemoryModule(
        container=container,
        event_bus=event_bus,
        store=in_memory_store,
    )
    mem_module.semantic.add_fact(
        Fact(subject="usuario", predicate="nombre", object_val="Andrés", source="user")
    )
    mem_module.semantic.add_fact(
        Fact(
            subject="usuario",
            predicate="actividad",
            object_val="estudiando ingeniería software",
            source="user",
        )
    )
    container.register(MemoryModule, instance=mem_module)

    builder = CognitiveContextBuilder(container=container)
    ctx = builder.build(input_text="¿Qué recuerdas de mí?")

    assert len(ctx.relevant_memories) >= 2
    memories_str = " ".join(ctx.relevant_memories)
    assert "Andrés" in memories_str
    assert "ingeniería software" in memories_str

    prompt = ctx.to_system_prompt()
    assert "RECUERDOS DE MEMORIA PERSISTENTE DEL USUARIO:" in prompt
    assert "Andrés" in prompt
    assert "ingeniería software" in prompt
