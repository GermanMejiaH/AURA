from __future__ import annotations

from pathlib import Path

from aura import AURA, AURABootOptions
from aura.cognition import CognitionModule
from aura.config import ConfigurationManager
from aura.memory import MemoryModule


def test_e2e_datetime_tool_orchestration(tmp_path: Path) -> None:
    db_file = str(tmp_path / "datetime_e2e.db")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)
    assert cog is not None

    res = cog.process_cognitive_cycle("¿Qué hora es?")

    # Verify context built system prompt contains tool output
    assert res.summary is not None
    assert cog.working_memory.get_recent_conversation(limit=2) is not None

    aura.shutdown(wait=True)


def test_e2e_calculator_tool_orchestration(tmp_path: Path) -> None:
    db_file = str(tmp_path / "calc_e2e.db")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)
    assert cog is not None

    res = cog.process_cognitive_cycle("¿Cuánto es 125 * 37?")
    assert res.summary is not None

    aura.shutdown(wait=True)


def test_e2e_greeting_skips_tools_and_memory(tmp_path: Path) -> None:
    db_file = str(tmp_path / "greeting_e2e.db")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)
    mem = aura.container.resolve(MemoryModule)
    assert cog is not None and mem is not None

    mem.preferences.set_preference("comida_favorita", "la pizza")

    # Turn 1: Greeting -> No tools, no persistent memory query
    cog.process_cognitive_cycle("Hola AURA")
    ctx_greeting = cog.context_builder.build("Hola AURA", working_memory=cog.working_memory)
    assert len(ctx_greeting.relevant_memories) == 0
    assert len(ctx_greeting.tool_results) == 0

    # Turn 2: Personal Memory Query -> Persistent memory query active, no tools
    cog.process_cognitive_cycle("¿Cuál es mi comida favorita?")
    ctx_mem = cog.context_builder.build(
        "¿Cuál es mi comida favorita?", working_memory=cog.working_memory
    )
    assert len(ctx_mem.relevant_memories) > 0

    aura.shutdown(wait=True)
