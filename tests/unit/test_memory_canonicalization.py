from __future__ import annotations

from pathlib import Path

from aura.cognition.memory_detector import ExplicitMemoryDetector
from aura.events import EventBus
from aura.memory import (
    EpisodicMemory,
    MemoryRetrievalEngine,
    SQLiteMemoryStore,
    UserPreferencesMemory,
    canonicalize_key,
)


def test_canonicalize_key_basic() -> None:
    assert canonicalize_key("comida_favorita_ahora") == "comida_favorita"
    assert canonicalize_key("comida_preferida") == "comida_favorita"
    assert canonicalize_key("mi_comida_favorita") == "comida_favorita"
    assert canonicalize_key("color_favorito_ahora") == "color_favorito"
    assert canonicalize_key("color_preferido") == "color_favorito"
    assert canonicalize_key("mi_color_favorito") == "color_favorito"
    assert canonicalize_key("pelicula_favorita_ahora") == "pelicula_favorita"
    assert canonicalize_key("pelicula_preferida") == "pelicula_favorita"
    assert canonicalize_key("cumpleanos") == "cumpleaños"


def test_explicit_memory_detector_canonicalization() -> None:
    # TEST 1
    d1 = ExplicitMemoryDetector.detect("Recuerda que mi comida favorita ahora es la hamburguesa.")
    assert d1.detected is True
    assert d1.predicate == "comida_favorita"
    assert d1.object_val == "la hamburguesa"

    # TEST 2
    d2 = ExplicitMemoryDetector.detect("Ahora mi comida favorita es la pizza.")
    assert d2.detected is True
    assert d2.predicate == "comida_favorita"
    assert d2.object_val == "la pizza"


def test_user_preferences_alias_cleaning(tmp_path: Path) -> None:
    db_file = str(tmp_path / "pref_alias.db")
    store = SQLiteMemoryStore(db_path=db_file)
    bus = EventBus()
    prefs = UserPreferencesMemory(event_bus=bus, store=store)

    # TEST 3: Store comida_favorita_ahora = hamburguesa, then comida_favorita = pizza
    prefs.set_preference("comida_favorita_ahora", "hamburguesa")

    # Verify initial alias state
    all_p1 = prefs.all_preferences()
    assert len(all_p1) == 1

    # Store update
    prefs.set_preference("comida_favorita", "pizza")

    # Final state in RAM must contain ONLY comida_favorita = pizza
    all_p2 = prefs.all_preferences()
    assert len(all_p2) == 1
    assert all_p2[0].key == "comida_favorita"
    assert all_p2[0].value == "pizza"

    store.close()

    # TEST 4: Rebuild UserPreferencesMemory from SQLite and check get_preference
    store2 = SQLiteMemoryStore(db_path=db_file)
    prefs2 = UserPreferencesMemory(event_bus=bus, store=store2)
    val = prefs2.get_preference("comida_favorita")
    assert val == "pizza"

    # Ensure comida_favorita_ahora key does NOT exist in SQLite
    db_prefs = store2.get_all_preferences()
    assert len(db_prefs) == 1
    assert db_prefs[0].key == "comida_favorita"
    assert db_prefs[0].value == "pizza"
    store2.close()


def test_retrieval_does_not_return_obsolete_preference_alias(tmp_path: Path) -> None:
    db_file = str(tmp_path / "retrieval_alias.db")
    store = SQLiteMemoryStore(db_path=db_file)
    bus = EventBus()

    episodic = EpisodicMemory(event_bus=bus, store=store)
    from aura.memory import SemanticMemory

    semantic = SemanticMemory(event_bus=bus, store=store)
    prefs = UserPreferencesMemory(event_bus=bus, store=store)

    # TEST 5: Populate comida_favorita = pizza
    prefs.set_preference("comida_favorita", "la pizza")

    engine = MemoryRetrievalEngine(
        episodic=episodic,
        semantic=semantic,
        preferences=prefs,
        event_bus=bus,
    )

    # Query: "¿Cuál es mi comida ahorita?"
    res = engine.query("¿Cuál es mi comida ahorita?")
    assert len(res.preferences) == 1
    assert res.preferences[0].key == "comida_favorita"
    assert res.preferences[0].value == "la pizza"

    store.close()
