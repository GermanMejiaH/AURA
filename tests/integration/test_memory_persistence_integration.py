from __future__ import annotations

from pathlib import Path

from aura import AURA, AURABootOptions
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

    from aura.cognition import CognitionModule

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
