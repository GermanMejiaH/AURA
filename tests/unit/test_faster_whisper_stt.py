from __future__ import annotations

from unittest.mock import MagicMock, patch

from aura.audio import FasterWhisperSTTProvider
from aura.events import EventBus, SpeechRecognized
from aura.memory import UserPreferencesMemory


def test_faster_whisper_stt_provider_mocked_transcription():
    bus = EventBus()
    events: list[SpeechRecognized] = []
    bus.subscribe("SpeechRecognized", lambda e: events.append(e))

    mock_segment = MagicMock()
    mock_segment.text = "Hola AURA"
    mock_segment.avg_logprob = -0.1

    mock_info = MagicMock()
    mock_info.language = "es"

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    with patch("faster_whisper.WhisperModel", return_value=mock_model):
        stt = FasterWhisperSTTProvider(model_size_or_path="tiny", event_bus=bus)
        result = stt.transcribe(b"dummy_wav_bytes", language="es")

        assert result.text == "Hola AURA"
        assert result.language == "es"
        assert len(events) == 1
        assert events[0].text == "Hola AURA"


def test_faster_whisper_adaptive_vocabulary():
    prefs = UserPreferencesMemory()
    stt = FasterWhisperSTTProvider(model_size_or_path="tiny", preferences_memory=prefs)

    stt.add_vocabulary_word("Andrés")
    stt.add_vocabulary_word("AURA Core")

    prompt = stt._get_effective_prompt()
    assert "Andrés" in prompt
    assert "AURA Core" in prompt
    assert prefs.get_preference("speech_vocabulary") == "Andrés, AURA Core"
