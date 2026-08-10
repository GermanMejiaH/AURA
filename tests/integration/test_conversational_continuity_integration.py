from __future__ import annotations

from pathlib import Path

from aura import AURA, AURABootOptions
from aura.cognition import CognitionModule
from aura.config import ConfigurationManager
from aura.memory import MemoryModule


def test_consecutive_turns_context_continuity(tmp_path: Path) -> None:
    db_file = str(tmp_path / "continuity_test.db")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)
    assert cog is not None

    # Turn 1: User introduces name
    cog.process_cognitive_cycle("Me llamo Carlos.")

    # Turn 2: Anaphoric query check
    ctx2 = cog.context_builder.build("¿Cuál es mi nombre?", working_memory=cog.working_memory)
    prompt2 = ctx2.to_formatted_prompt()

    assert "Me llamo Carlos." in prompt2
    assert "[Usuario]: Me llamo Carlos." in prompt2

    aura.shutdown(wait=True)


def test_anaphoric_reference_context_building(tmp_path: Path) -> None:
    db_file = str(tmp_path / "anaphora_test.db")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)
    assert cog is not None

    # Turn 1: Introduce pet name
    cog.process_cognitive_cycle("Mi perro se llama Firulais.")

    # Turn 2: Anaphoric question ("¿Y él qué edad tiene?")
    ctx2 = cog.context_builder.build("¿Y él qué edad tiene?", working_memory=cog.working_memory)
    prompt2 = ctx2.to_formatted_prompt()

    assert "Mi perro se llama Firulais." in prompt2
    assert "Usuario: ¿Y él qué edad tiene?" in prompt2

    aura.shutdown(wait=True)


def test_casual_banter_memory_isolation(tmp_path: Path) -> None:
    db_file = str(tmp_path / "banter_isolation.db")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)
    mem = aura.container.resolve(MemoryModule)
    assert cog is not None and mem is not None

    cog.process_cognitive_cycle("Hola AURA")
    cog.process_cognitive_cycle("¿Cómo estás?")
    cog.process_cognitive_cycle("Qué buen día hace hoy")

    # Working Memory must contain 6 turns (3 user + 3 assistant)
    assert len(cog.working_memory.get_recent_conversation()) == 6

    # Semantic and Preferences memory must remain EMPTY (0 facts/preferences)
    assert len(mem.semantic.all_facts()) == 0
    assert len(mem.preferences.all_preferences()) == 0

    aura.shutdown(wait=True)


def test_reboot_clears_working_memory_retains_persistent_facts(tmp_path: Path) -> None:
    db_file = str(tmp_path / "reboot_coexistence.db")

    # SESSION 1: Store explicit fact
    cfg1 = ConfigurationManager()
    cfg1.set("memory.db_path", db_file)
    cfg1.set("llm.provider", "mock")

    aura1 = AURA(config=cfg1, options=AURABootOptions())
    aura1.boot()
    cog1 = aura1.container.resolve(CognitionModule)
    assert cog1 is not None

    cog1.process_cognitive_cycle("Recuerda que mi comida favorita es la pizza.")
    aura1.shutdown(wait=True)

    # SESSION 2: Reboot AURA with same DB
    cfg2 = ConfigurationManager()
    cfg2.set("memory.db_path", db_file)
    cfg2.set("llm.provider", "mock")

    aura2 = AURA(config=cfg2, options=AURABootOptions())
    aura2.boot()

    cog2 = aura2.container.resolve(CognitionModule)
    assert cog2 is not None

    # Working Memory must start completely empty (0 turns)
    assert len(cog2.working_memory.get_recent_conversation()) == 0

    # Casual conversation in session 2
    cog2.process_cognitive_cycle("Hola AURA, ¿cómo estás hoy?")

    # Query persistent memory in turn 2 of session 2
    ctx = cog2.context_builder.build(
        "¿Cuál es mi comida favorita?", working_memory=cog2.working_memory
    )
    sys_prompt = ctx.to_system_prompt()
    formatted_prompt = ctx.to_formatted_prompt()

    # System prompt must contain persistent fact from session 1
    assert "la pizza" in sys_prompt.lower()
    # Formatted prompt must contain recent session 2 history
    assert "Hola AURA, ¿cómo estás hoy?" in formatted_prompt

    aura2.shutdown(wait=True)
