from __future__ import annotations

from aura.audio import AudioModule
from aura.cognition import CognitiveState, CognitiveStateMachine
from aura.core import AURA, AURABootOptions, SystemState
from aura.events import SpeechRecognized, WakeWordDetected


def test_audio_module_voice_conversation_integration(tmp_path):
    options = AURABootOptions(
        enable_scheduler=False,
        enable_health_monitor=False,
        enable_cwm=True,
        enable_cognition=True,
        enable_audio=True,
    )
    aura = AURA(options=options)
    aura.config.set("cwm.storage_path", str(tmp_path / "cwm.json"))
    aura.boot()

    assert aura.state == SystemState.RUNNING

    # Resolve AudioModule and CognitiveStateMachine
    audio_mod = aura.module_manager.get("audio")
    assert audio_mod is not None
    assert isinstance(audio_mod, AudioModule)

    sm = aura.container.resolve(CognitiveStateMachine)

    # Test wake word trigger transition
    wakeword_events: list[WakeWordDetected] = []
    speech_events: list[SpeechRecognized] = []
    aura.subscribe("WakeWordDetected", lambda e: wakeword_events.append(e))
    aura.subscribe("SpeechRecognized", lambda e: speech_events.append(e))

    # Trigger wake word event through AudioModule
    res = audio_mod.wakeword.trigger(keyword="aura")
    if res.detected:
        audio_mod.publish(WakeWordDetected(source="AudioModule", keyword=res.keyword))
    assert sm.state == CognitiveState.LISTENING

    # Trigger voice interaction turn
    response_text = audio_mod.trigger_voice_interaction("¿Cuál es el estado del sistema?")
    assert isinstance(response_text, str)
    assert len(response_text) > 0
    assert sm.state == CognitiveState.IDLE

    aura.shutdown(wait=True)
    assert aura.state == SystemState.STOPPED
