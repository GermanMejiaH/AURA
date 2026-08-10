from __future__ import annotations

from aura.audio import AudioData, AudioModule
from aura.cognition import CognitionModule
from aura.core.aura import AURA, AURABootOptions
from aura.events import Event


def test_aura_vertical_slice_conversational_turn():
    published_events: list[Event] = []

    options = AURABootOptions(
        auto_discover_modules=False,
        module_classes=(CognitionModule, AudioModule),
    )
    aura = AURA(options=options)
    aura.boot()

    # Subscribe to domain events to verify pipeline execution
    aura.event_bus.subscribe("*", lambda e: published_events.append(e))

    # Retrieve AudioModule instance
    audio_mod = aura.module_manager.get("audio")
    assert isinstance(audio_mod, AudioModule)

    # 1. Create simulated audio input
    input_text = "Hola AURA, ¿cuál es tu estado actual?"
    audio_input = AudioData.create_mock(text=input_text, duration=1.5)

    # 2. Execute full conversational turn
    turn_result = audio_mod.process_conversational_turn(audio_input)

    # 3. Verify turn output
    assert turn_result.recognized_text == input_text
    assert turn_result.response_text != ""
    assert turn_result.audio_output is not None
    assert len(turn_result.audio_output) > 0

    # 4. Verify domain event publications
    event_names = [e.event_name() for e in published_events]
    assert "SpeechRecognized" in event_names
    assert "SpeechSynthesized" in event_names
    assert "AudioPlaybackStarted" in event_names
    assert "AudioPlaybackFinished" in event_names

    # 5. Shutdown system cleanly
    shutdown_ok = aura.shutdown(wait=True, timeout=5.0)
    assert shutdown_ok is True
