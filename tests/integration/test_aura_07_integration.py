from __future__ import annotations

from pathlib import Path

from aura import AURA, AURABootOptions
from aura.cognition import CognitionModule
from aura.config import ConfigurationManager
from aura.memory import MemoryModule


def test_greeting_skips_persistent_memory_retrieval(tmp_path: Path) -> None:
    db_file = str(tmp_path / "greeting_retrieval.db")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)
    mem = aura.container.resolve(MemoryModule)
    assert cog is not None and mem is not None

    # Pre-populate SQLite with persistent memory
    mem.preferences.set_preference("comida_favorita", "pasta")

    # Cycle 1: Greeting
    ctx_greeting = cog.context_builder.build(
        "Hola AURA", working_memory=cog.working_memory
    )
    # Greeting context must NOT contain relevant persistent memories list
    assert len(ctx_greeting.relevant_memories) == 0

    # Cycle 2: Memory Query
    ctx_query = cog.context_builder.build(
        "¿Cuál es mi comida favorita?", working_memory=cog.working_memory
    )
    # Memory Query context MUST contain persistent memories list
    assert len(ctx_query.relevant_memories) > 0
    assert "pasta" in ctx_query.to_system_prompt().lower()

    aura.shutdown(wait=True)


def test_anaphoric_pet_reference_and_coexistence(tmp_path: Path) -> None:
    db_file = str(tmp_path / "pet_anaphora.db")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)
    assert cog is not None

    # Turn 1: Memory Update
    cog.process_cognitive_cycle(
        "Recuerda que mi perra se llama Lila."
    )

    # Turn 2: Memory Query with personal indicator
    ctx2 = cog.context_builder.build(
        "¿Cómo se llama mi perra?", working_memory=cog.working_memory
    )
    sys_prompt = ctx2.to_system_prompt()

    assert "lila" in sys_prompt.lower() or "perra" in sys_prompt.lower()

    aura.shutdown(wait=True)
