from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from aura.memory import Episode, Fact, Preference, SQLiteMemoryStore


def test_sqlite_memory_store_fact_crud(tmp_path: Path) -> None:
    db_file = str(tmp_path / "test_facts.db")
    store = SQLiteMemoryStore(db_path=db_file)

    fact = Fact(
        subject="usuario",
        predicate="color_favorito",
        object_val="azul",
        confidence=1.0,
        source="user",
        created_at=datetime.now(UTC),
    )
    store.save_fact(fact)

    facts = store.get_facts(subject="usuario")
    assert len(facts) == 1
    assert facts[0].object_val == "azul"
    assert facts[0].predicate == "color_favorito"

    deleted = store.delete_fact(fact.id)
    assert deleted is True
    assert len(store.get_facts()) == 0
    store.close()


def test_sqlite_memory_store_preference_crud(tmp_path: Path) -> None:
    db_file = str(tmp_path / "test_prefs.db")
    store = SQLiteMemoryStore(db_path=db_file)

    pref = Preference(key="tema", value="oscuro", category="ui")
    store.save_preference(pref)

    retrieved = store.get_preference("tema")
    assert retrieved is not None
    assert retrieved.value == "oscuro"
    assert len(store.get_all_preferences()) == 1
    store.close()


def test_sqlite_memory_store_episode_crud(tmp_path: Path) -> None:
    db_file = str(tmp_path / "test_episodes.db")
    store = SQLiteMemoryStore(db_path=db_file)

    episode = Episode(summary="Conversación sobre AURA", details="Detalles del turno")
    store.save_episode(episode)

    episodes = store.get_episodes(query="AURA")
    assert len(episodes) == 1
    assert episodes[0].summary == "Conversación sobre AURA"
    store.close()


def test_sqlite_persistence_across_reopen(tmp_path: Path) -> None:
    db_file = str(tmp_path / "persisted.db")

    # Session 1: Store data & close
    store1 = SQLiteMemoryStore(db_path=db_file)
    store1.save_fact(Fact(subject="usuario", predicate="carrera", object_val="Ingeniería"))
    store1.save_preference(Preference(key="lenguaje", value="Spanish"))
    store1.close()

    assert os.path.exists(db_file)

    # Session 2: Reopen & verify
    store2 = SQLiteMemoryStore(db_path=db_file)
    facts = store2.get_facts(subject="usuario")
    pref = store2.get_preference("lenguaje")

    assert len(facts) == 1
    assert facts[0].object_val == "Ingeniería"
    assert pref is not None
    assert pref.value == "Spanish"
    store2.close()
