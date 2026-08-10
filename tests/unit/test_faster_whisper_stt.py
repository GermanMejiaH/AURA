from __future__ import annotations

from unittest.mock import MagicMock, patch

from aura.audio import FasterWhisperSTTProvider
from aura.memory import UserPreferencesMemory


def test_faster_whisper_stt_provider_mocked_transcription():
    mock_segment = MagicMock()
    mock_segment.text = "Hola AURA"
    mock_segment.avg_logprob = -0.1

    mock_info = MagicMock()
    mock_info.language = "es"

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    with patch("faster_whisper.WhisperModel", return_value=mock_model):
        stt = FasterWhisperSTTProvider(model_size_or_path="tiny")
        result = stt.transcribe(b"dummy_wav_bytes", language="es")

        assert result.text == "Hola AURA"
        assert result.language == "es"


def test_faster_whisper_adaptive_vocabulary():
    prefs = UserPreferencesMemory()
    stt = FasterWhisperSTTProvider(model_size_or_path="tiny", preferences_memory=prefs)

    stt.add_vocabulary_word("Andrés")
    stt.add_vocabulary_word("AURA Core")

    prompt = stt._get_effective_prompt()
    assert "Andrés" in prompt
    assert "AURA Core" in prompt
    assert prefs.get_preference("speech_vocabulary") == "Andrés, AURA Core"


def test_faster_whisper_cuda_runtime_error_fallback() -> None:
    mock_cuda_model = MagicMock()
    mock_cuda_model.transcribe.side_effect = RuntimeError("Library cublas64_12.dll is not found")

    mock_cpu_segment = MagicMock()
    mock_cpu_segment.text = "Transcripción CPU exitosa"
    mock_cpu_segment.avg_logprob = -0.05
    mock_cpu_info = MagicMock()
    mock_cpu_info.language = "es"

    mock_cpu_model = MagicMock()
    mock_cpu_model.transcribe.return_value = ([mock_cpu_segment], mock_cpu_info)

    def model_factory(model_size: str, device: str, **kwargs: object) -> MagicMock:
        if device == "cuda":
            return mock_cuda_model
        return mock_cpu_model

    with patch("faster_whisper.WhisperModel", side_effect=model_factory):
        stt = FasterWhisperSTTProvider(model_size_or_path="tiny", device="cuda")
        result = stt.transcribe(b"dummy_wav_bytes", language="es")

        assert result.text == "Transcripción CPU exitosa"
        assert stt.device == "cpu"
