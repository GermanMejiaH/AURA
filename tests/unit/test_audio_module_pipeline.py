from __future__ import annotations

from aura.audio.input import MockAudioInputProvider
from aura.audio.module import AudioModule
from aura.audio.output import MockAudioOutputProvider
from aura.audio.stt import MockSTTProvider, STTResult
from aura.audio.tts import MockTTSProvider, TTSResult
from aura.audio.types import AudioData
from aura.cognition import CognitionModule
from aura.container import DependencyContainer


def test_audio_module_push_to_talk_turn_with_metrics() -> None:
    container = DependencyContainer()

    # Register CognitionModule
    cog = CognitionModule(container=container)
    cog.initialize()
    cog.start()

    input_prov = MockAudioInputProvider(mock_text="¿Hola AURA cómo estás?", mock_duration=1.2)
    output_prov = MockAudioOutputProvider()
    stt_prov = MockSTTProvider(default_transcript="¿Hola AURA cómo estás?")
    tts_prov = MockTTSProvider()

    module = AudioModule(
        container=container,
        audio_input=input_prov,
        audio_output=output_prov,
        stt_provider=stt_prov,
        tts_provider=tts_prov,
    )
    module.initialize()
    module.start()

    assert not module.is_capturing_voice()
    module.start_voice_capture()
    assert module.is_capturing_voice()

    turn = module.stop_voice_capture_and_process(playback=True)
    assert not module.is_capturing_voice()

    assert turn.recognized_text == "¿Hola AURA cómo estás?"
    assert turn.response_text != ""
    assert output_prov.last_played_bytes is not None

    m = turn.metrics
    assert m.capture_sec >= 0.0
    assert m.stt_sec >= 0.0
    assert m.cognition_sec >= 0.0
    assert m.tts_sec >= 0.0
    assert m.playback_sec >= 0.0
    assert m.total_sec >= 0.0

    module.stop()
    module.shutdown()
    cog.stop()
    cog.shutdown()


def test_audio_module_empty_stt_transcription_handling() -> None:
    input_prov = MockAudioInputProvider()
    output_prov = MockAudioOutputProvider()

    class EmptySTT(MockSTTProvider):
        def transcribe(self, audio: AudioData | bytes, language: str = "es") -> STTResult:
            return STTResult(text="", confidence=0.0)

    module = AudioModule(
        audio_input=input_prov,
        audio_output=output_prov,
        stt_provider=EmptySTT(),
    )
    module.initialize()
    module.start()

    module.start_voice_capture()
    turn = module.stop_voice_capture_and_process(playback=True)

    assert turn.recognized_text == ""
    assert turn.response_text == ""
    assert output_prov.last_played_bytes is None
    assert turn.metrics.stt_sec >= 0.0

    module.stop()
    module.shutdown()


def test_audio_module_tts_error_resilience() -> None:
    input_prov = MockAudioInputProvider(mock_text="Test TTS error")
    output_prov = MockAudioOutputProvider()

    class ErrorTTS(MockTTSProvider):
        def synthesize(self, text: str, voice: str = "default") -> TTSResult:
            return TTSResult(audio_bytes=b"", text=text, duration_seconds=0.0)

    module = AudioModule(
        audio_input=input_prov,
        audio_output=output_prov,
        tts_provider=ErrorTTS(),
    )
    module.initialize()
    module.start()

    turn = module.process_conversational_turn(AudioData.create_mock(text="Hola"), playback=True)
    assert turn.recognized_text == "Hola"
    assert turn.audio_output == b""

    module.stop()
    module.shutdown()
