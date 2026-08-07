from __future__ import annotations

from aura.core import AURA, AURABootOptions, SystemState
from aura.events import EpisodeRecorded
from aura.memory import EpisodicMemory, MemoryModule


def test_memory_module_integration(tmp_path):
    options = AURABootOptions(
        enable_scheduler=False,
        enable_health_monitor=False,
        enable_cwm=True,
        enable_cognition=True,
        enable_audio=True,
        enable_vision=True,
        enable_memory=True,
    )
    aura = AURA(options=options)
    aura.config.set("cwm.storage_path", str(tmp_path / "cwm.json"))
    aura.boot()

    assert aura.state == SystemState.RUNNING

    mem_mod = aura.module_manager.get("memory")
    assert mem_mod is not None
    assert isinstance(mem_mod, MemoryModule)

    recorded_events: list[EpisodeRecorded] = []
    aura.subscribe("EpisodeRecorded", lambda e: recorded_events.append(e))

    # Publish a speech event to verify automatic episode logging
    from aura.events import SpeechRecognized

    aura.publish(SpeechRecognized(text="Hola AURA desde pruebas"))

    episodic = aura.container.resolve(EpisodicMemory)
    assert episodic.count() >= 1
    assert len(recorded_events) >= 1

    aura.shutdown(wait=True)
    assert aura.state == SystemState.STOPPED
