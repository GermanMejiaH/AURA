from __future__ import annotations

from unittest.mock import MagicMock, patch

from aura.audio import WhisperWakeWordDetector
from aura.audio.wakeword import WakeWordResult
from aura.events import EventBus


def test_whisper_wakeword_detector_is_not_active_initially():
    detector = WhisperWakeWordDetector()
    assert not detector.is_active()


def test_whisper_wakeword_detector_start_stop():
    detector = WhisperWakeWordDetector()

    with patch.object(detector, "_listen_loop", return_value=None):
        detector.start()
        assert detector.is_active()
        detector.stop()
        assert not detector.is_active()


def test_whisper_wakeword_detector_keyword_match():
    detector = WhisperWakeWordDetector(keywords=["aura"])
    mock_model = MagicMock()

    mock_segment = MagicMock()
    mock_segment.text = "hola aura como estás"
    mock_info = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    # Write a tiny silent WAV (44 bytes header only)
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)
    audio_bytes = buf.getvalue()

    result = detector._check_for_keyword(mock_model, audio_bytes)
    assert result.detected
    assert result.keyword == "aura"


def test_whisper_wakeword_detector_no_keyword():
    detector = WhisperWakeWordDetector(keywords=["aura"])
    mock_model = MagicMock()

    mock_segment = MagicMock()
    mock_segment.text = "el perro corre en el parque"
    mock_model.transcribe.return_value = ([mock_segment], MagicMock())

    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)
    audio_bytes = buf.getvalue()

    result = detector._check_for_keyword(mock_model, audio_bytes)
    assert not result.detected


def test_whisper_wakeword_fires_callback():
    callback_called: list[WakeWordResult] = []

    detector = WhisperWakeWordDetector(
        keywords=["aura"],
        on_detected=lambda r: callback_called.append(r),
    )

    wake_result = WakeWordResult(detected=True, keyword="aura", confidence=0.90)
    detector._fire_detected(wake_result)

    assert len(callback_called) == 1
    assert callback_called[0].keyword == "aura"


def test_whisper_wakeword_fires_event_bus():
    bus = EventBus()
    events = []
    bus.subscribe("WakeWordDetected", lambda e: events.append(e))

    detector = WhisperWakeWordDetector(keywords=["aura"], event_bus=bus)
    wake_result = WakeWordResult(detected=True, keyword="aura", confidence=0.90)
    detector._fire_detected(wake_result)

    assert len(events) == 1
    assert events[0].keyword == "aura"
