from __future__ import annotations

from pathlib import Path

from aura import AURA, AURABootOptions
from aura.cognition import CognitionModule
from aura.config import ConfigurationManager
from aura.memory import SQLiteMemoryStore


def test_full_memory_persistence_across_sessions(tmp_path: Path) -> None:
    db_file = str(tmp_path / "integration_aura.db")

    # ==========================================
    # SESSION 1: User teaches AURA a fact
    # ==========================================
    cfg1 = ConfigurationManager()
    cfg1.set("memory.db_path", db_file)
    cfg1.set("llm.provider", "mock")

    aura1 = AURA(config=cfg1, options=AURABootOptions())
    aura1.boot()

    cog1 = aura1.container.resolve(CognitionModule)
    assert cog1 is not None

    # Turn 1: User explicitly requests to remember a fact
    turn1 = cog1.process_cognitive_cycle(
        "AURA, recuerda que estoy estudiando Ingeniería de Software"
    )
    assert "recordaré" in turn1.summary.lower() or "estudiando" in turn1.summary.lower()

    aura1.shutdown(wait=True)

    # Verify that SQLite DB file was populated
    store_checker = SQLiteMemoryStore(db_path=db_file)
    facts = store_checker.get_facts(subject="usuario")
    assert len(facts) >= 1
    assert any("ingeniería de software" in f.object_val.lower() for f in facts)
    store_checker.close()

    # ==========================================
    # SESSION 2: Reboot AURA with same DB
    # ==========================================
    cfg2 = ConfigurationManager()
    cfg2.set("memory.db_path", db_file)
    cfg2.set("llm.provider", "mock")

    aura2 = AURA(config=cfg2, options=AURABootOptions())
    aura2.boot()

    cog2 = aura2.container.resolve(CognitionModule)
    assert cog2 is not None

    # Context builder should extract the fact from SQLite
    ctx = cog2.context_builder.build("¿Qué estoy estudiando?")
    sys_prompt = ctx.to_system_prompt()

    assert "ingeniería de software" in sys_prompt.lower()

    aura2.shutdown(wait=True)


def test_voice_preamble_memory_persistence(tmp_path: Path) -> None:
    db_file = str(tmp_path / "voice_preamble.db")

    # ==========================================
    # SESSION 1: User uses natural preamble from real STT
    # "Ahora, recuerda que mi color favorito es el rojo."
    # ==========================================
    cfg1 = ConfigurationManager()
    cfg1.set("memory.db_path", db_file)
    cfg1.set("llm.provider", "mock")

    aura1 = AURA(config=cfg1, options=AURABootOptions())
    aura1.boot()

    cog1 = aura1.container.resolve(CognitionModule)
    assert cog1 is not None

    turn1 = cog1.process_cognitive_cycle("Ahora, recuerda que mi color favorito es el rojo.")
    assert "recordaré" in turn1.summary.lower() or "registrado" in turn1.summary.lower()

    aura1.shutdown(wait=True)

    # Verify SQLite on disk
    store_checker = SQLiteMemoryStore(db_path=db_file)
    facts = store_checker.get_facts(subject="usuario", predicate="color_favorito")
    assert len(facts) == 1
    assert facts[0].object_val == "el rojo"
    store_checker.close()

    # ==========================================
    # SESSION 2: Reboot AURA with same DB and ask question
    # ==========================================
    cfg2 = ConfigurationManager()
    cfg2.set("memory.db_path", db_file)
    cfg2.set("llm.provider", "mock")

    aura2 = AURA(config=cfg2, options=AURABootOptions())
    aura2.boot()

    cog2 = aura2.container.resolve(CognitionModule)
    assert cog2 is not None

    ctx = cog2.context_builder.build("¿Cuál es mi color favorito?")
    sys_prompt = ctx.to_system_prompt()

    assert "color_favorito del usuario" in sys_prompt.lower()
    assert "el rojo" in sys_prompt.lower()

    aura2.shutdown(wait=True)


def test_comida_favorita_update_persistence(tmp_path: Path) -> None:
    db_file = str(tmp_path / "comida_update.db")

    # ==========================================
    # SESSION 1: User teaches pizza, then updates to hamburguesa
    # ==========================================
    cfg1 = ConfigurationManager()
    cfg1.set("memory.db_path", db_file)
    cfg1.set("llm.provider", "mock")

    aura1 = AURA(config=cfg1, options=AURABootOptions())
    aura1.boot()

    cog1 = aura1.container.resolve(CognitionModule)
    assert cog1 is not None

    cog1.process_cognitive_cycle("Recuerda que mi comida favorita es la pizza.")
    cog1.process_cognitive_cycle("Ahora mi comida favorita es la hamburguesa.")

    aura1.shutdown(wait=True)

    # Verify SQLite DB contains ONLY 1 fact for comida_favorita ("la hamburguesa")
    store_checker = SQLiteMemoryStore(db_path=db_file)
    facts = store_checker.get_facts(subject="usuario", predicate="comida_favorita")
    assert len(facts) == 1
    assert facts[0].object_val == "la hamburguesa"
    store_checker.close()

    # ==========================================
    # SESSION 2: Reboot AURA with same DB and ask question
    # ==========================================
    cfg2 = ConfigurationManager()
    cfg2.set("memory.db_path", db_file)
    cfg2.set("llm.provider", "mock")

    aura2 = AURA(config=cfg2, options=AURABootOptions())
    aura2.boot()

    cog2 = aura2.container.resolve(CognitionModule)
    assert cog2 is not None

    ctx = cog2.context_builder.build("¿Cuál es mi comida favorita?")
    sys_prompt = ctx.to_system_prompt()

    assert "comida_favorita del usuario" in sys_prompt.lower()
    assert "la hamburguesa" in sys_prompt.lower()
    assert "la pizza" not in sys_prompt.lower()

    aura2.shutdown(wait=True)


def test_multi_step_food_update_sequence_and_independence(tmp_path: Path) -> None:
    db_file = str(tmp_path / "multi_step_food.db")

    # ==========================================
    # SESSION 1: Direct statement (pizza), Update 1 (hamburguesa), Update 2 (pasta), and Alias check
    # ==========================================
    cfg1 = ConfigurationManager()
    cfg1.set("memory.db_path", db_file)
    cfg1.set("llm.provider", "mock")

    aura1 = AURA(config=cfg1, options=AURABootOptions())
    aura1.boot()

    cog1 = aura1.container.resolve(CognitionModule)
    assert cog1 is not None

    # Independent fact: color_favorito
    cog1.process_cognitive_cycle("Recuerda que mi color favorito es el verde.")

    # Step 1: Direct statement (pizza)
    cog1.process_cognitive_cycle("Mi comida favorita es la pizza.")

    # Step 2: Update 1 (hamburguesa)
    cog1.process_cognitive_cycle("Ahora mi comida favorita es la hamburguesa.")

    # Step 3: Update 2 (pasta)
    cog1.process_cognitive_cycle("Ahora mi comida favorita es la pasta.")

    # Step 4: Alias directive check
    cog1.process_cognitive_cycle("Recuerda que mi comida favorita ahora es la pasta.")

    aura1.shutdown(wait=True)

    # Verify SQLite DB directly
    store_checker = SQLiteMemoryStore(db_path=db_file)
    facts = store_checker.get_facts(subject="usuario", predicate="comida_favorita")
    assert len(facts) == 1
    assert facts[0].object_val == "la pasta"

    prefs = store_checker.get_all_preferences()
    pref_keys = [p.key for p in prefs]
    assert "comida_favorita" in pref_keys
    assert "comida_favorita_ahora" not in pref_keys
    assert "color_favorito" in pref_keys

    store_checker.close()

    # ==========================================
    # SESSION 2: Reboot AURA with same DB and verify context
    # ==========================================
    cfg2 = ConfigurationManager()
    cfg2.set("memory.db_path", db_file)
    cfg2.set("llm.provider", "mock")

    aura2 = AURA(config=cfg2, options=AURABootOptions())
    aura2.boot()

    cog2 = aura2.container.resolve(CognitionModule)
    assert cog2 is not None

    ctx = cog2.context_builder.build("¿Cuál es mi comida favorita?")
    sys_prompt = ctx.to_system_prompt()

    assert "la pasta" in sys_prompt.lower()
    assert "el verde" in sys_prompt.lower()
    assert "la pizza" not in sys_prompt.lower()
    assert "la hamburguesa" not in sys_prompt.lower()

    aura2.shutdown(wait=True)
