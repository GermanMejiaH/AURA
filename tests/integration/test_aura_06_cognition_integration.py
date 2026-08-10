from __future__ import annotations

from pathlib import Path

from aura import AURA, AURABootOptions
from aura.cognition import CognitionModule
from aura.config import ConfigurationManager
from aura.events import EventBus, IntentDetected
from aura.memory import MemoryModule


def test_identity_isolation_from_user_memory(tmp_path: Path) -> None:
    db_file = str(tmp_path / "identity_isolation.db")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)
    mem = aura.container.resolve(MemoryModule)
    assert cog is not None and mem is not None

    # Change identity
    cog.identity_manager.update_identity(name="AURA Custom", personality_style="ultra formal")

    # User preferences in SQLite must remain completely empty
    assert len(mem.preferences.all_preferences()) == 0
    assert len(mem.semantic.all_facts()) == 0

    aura.shutdown(wait=True)


def test_user_memory_does_not_affect_aura_identity(tmp_path: Path) -> None:
    db_file = str(tmp_path / "memory_isolation.db")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)
    mem = aura.container.resolve(MemoryModule)
    assert cog is not None and mem is not None

    # Set user preference
    mem.preferences.set_preference("comida_favorita", "tacos")

    # AURA Identity must remain default
    identity = cog.identity_manager.get_identity()
    assert identity.name == "AURA"
    assert "tacos" not in identity.mission

    aura.shutdown(wait=True)


def test_reboot_clears_session_retains_persistent_memory(tmp_path: Path) -> None:
    db_file = str(tmp_path / "reboot_session_test.db")

    # Session 1: Store memory
    cfg1 = ConfigurationManager()
    cfg1.set("memory.db_path", db_file)
    cfg1.set("llm.provider", "mock")

    aura1 = AURA(config=cfg1, options=AURABootOptions())
    aura1.boot()
    cog1 = aura1.container.resolve(CognitionModule)
    assert cog1 is not None

    cog1.process_cognitive_cycle("Recuerda que mi comida favorita es la pizza.")
    sess_id_1 = cog1.session_manager.get_context().session_id
    aura1.shutdown(wait=True)

    # Session 2: Reboot
    cfg2 = ConfigurationManager()
    cfg2.set("memory.db_path", db_file)
    cfg2.set("llm.provider", "mock")

    aura2 = AURA(config=cfg2, options=AURABootOptions())
    aura2.boot()

    cog2 = aura2.container.resolve(CognitionModule)
    mem2 = aura2.container.resolve(MemoryModule)
    assert cog2 is not None and mem2 is not None

    sess_2 = cog2.session_manager.get_context()

    # Session ID must be new and turn count reset to 0
    assert sess_2.session_id != sess_id_1
    assert sess_2.turn_count == 0

    # Persistent memory must contain stored fact
    pref = mem2.preferences.get_preference("comida_favorita")
    assert pref == "la pizza"

    aura2.shutdown(wait=True)


def test_intent_event_bus_publishing(tmp_path: Path) -> None:
    db_file = str(tmp_path / "event_intent.db")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    bus = aura.container.resolve(EventBus)
    cog = aura.container.resolve(CognitionModule)
    assert bus is not None and cog is not None

    events_received: list[IntentDetected] = []

    def on_intent(evt: IntentDetected) -> None:
        events_received.append(evt)

    bus.subscribe(IntentDetected, on_intent)

    cog.process_cognitive_cycle("Hola AURA")

    assert len(events_received) == 1
    assert events_received[0].intent_type == "greeting"

    aura.shutdown(wait=True)
