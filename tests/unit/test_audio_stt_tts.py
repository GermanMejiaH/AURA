from aura.audio import AudioData, AudioModule, MockSTTProvider, MockTTSProvider
from aura.events import AudioPlaybackFinished, EventBus, SpeechRecognized, SpeechSynthesized


def test_stt_transcription_purity():
    stt = MockSTTProvider(default_transcript="Prueba de voz")
    result = stt.transcribe(b"dummy_audio")
    assert result.text == "Prueba de voz"


def test_tts_synthesis_purity():
    tts = MockTTSProvider()
    result = tts.synthesize("Hola mundo")
    assert result.audio_bytes == b"Hola mundo"


def test_audio_module_events():
    bus = EventBus()
    stt = MockSTTProvider(default_transcript="Prueba de voz")
    tts = MockTTSProvider()
    module = AudioModule(event_bus=bus, stt_provider=stt, tts_provider=tts)

    stt_events: list[SpeechRecognized] = []
    synth_events: list[SpeechSynthesized] = []
    finished_events: list[AudioPlaybackFinished] = []

    bus.subscribe("SpeechRecognized", lambda e: stt_events.append(e))  # type: ignore[arg-type]
    bus.subscribe("SpeechSynthesized", lambda e: synth_events.append(e))  # type: ignore[arg-type]
    bus.subscribe("AudioPlaybackFinished", lambda e: finished_events.append(e))  # type: ignore[arg-type]

    audio_data = AudioData.create_mock("Prueba de voz")
    turn = module.process_conversational_turn(audio_data)

    assert turn.recognized_text == "Prueba de voz"
    assert len(stt_events) == 1
    assert stt_events[0].text == "Prueba de voz"
    assert len(synth_events) == 1
    assert len(finished_events) == 1
