from __future__ import annotations

from aura.audio import MockSTTProvider, MockTTSProvider
from aura.events import AudioPlaybackFinished, EventBus, SpeechRecognized, SpeechSynthesized


def test_stt_transcription_and_event():
    bus = EventBus()
    stt = MockSTTProvider(default_transcript="Prueba de voz", event_bus=bus)

    events: list[SpeechRecognized] = []
    bus.subscribe("SpeechRecognized", lambda e: events.append(e))

    result = stt.transcribe(b"dummy_audio")
    assert result.text == "Prueba de voz"
    assert len(events) == 1
    assert events[0].text == "Prueba de voz"


def test_tts_synthesis_and_playback_events():
    bus = EventBus()
    tts = MockTTSProvider(event_bus=bus)

    synth_events: list[SpeechSynthesized] = []
    finished_events: list[AudioPlaybackFinished] = []
    bus.subscribe("SpeechSynthesized", lambda e: synth_events.append(e))
    bus.subscribe("AudioPlaybackFinished", lambda e: finished_events.append(e))

    result = tts.synthesize("Hola mundo")
    assert result.audio_bytes == b"Hola mundo"
    assert len(synth_events) == 1
    assert len(finished_events) == 1
    assert synth_events[0].text == "Hola mundo"
