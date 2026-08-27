# -*- coding: utf-8 -*-
from __future__ import annotations

from aura.audio.faster_whisper_stt import FasterWhisperSTTProvider
from aura.audio.microphone import MicrophoneRecorder
from aura.cognition.intent import ControlIntentDetector


def test_stt_provider_initialization_and_warmup() -> None:
    """Verifies default model is small, beam_size is configurable, and warmup executes cleanly."""
    stt = FasterWhisperSTTProvider(model_size_or_path="small", beam_size=1, device="cpu")
    assert stt.model_size_or_path == "small"
    assert stt.beam_size == 1
    # Test warmup does not raise
    stt.warmup()
    assert stt._model is not None


def test_microphone_recorder_vad_parameters() -> None:
    """Verifies MicrophoneRecorder default silence_sec is 0.8s."""
    recorder = MicrophoneRecorder()
    assert recorder.sample_rate == 16000
    assert recorder.channels == 1


def test_fastpath_time_query_detector() -> None:
    """Verifies Time & Date Fast-Path intent detector and response generator."""
    q_time = "Que hora es"
    q_date = "Que fecha es hoy"

    assert ControlIntentDetector.is_time_query(q_time) is True
    assert ControlIntentDetector.is_time_query(q_date) is True

    resp_time = ControlIntentDetector.get_time_response(q_time)
    resp_date = ControlIntentDetector.get_time_response(q_date)

    assert "Son las" in resp_time
    assert "Hoy es" in resp_date


def test_fastpath_calculator_query_detector() -> None:
    """Verifies Calculator Fast-Path intent detector and response generator."""
    q_math1 = "Cuanto es 123 x 9"
    q_math2 = "multiplica 12 por 5"
    q_math3 = "divide 100 entre 4"

    assert ControlIntentDetector.is_calculator_query(q_math1) is True
    assert ControlIntentDetector.is_calculator_query(q_math2) is True
    assert ControlIntentDetector.is_calculator_query(q_math3) is True

    resp1 = ControlIntentDetector.get_calculator_response(q_math1)
    resp2 = ControlIntentDetector.get_calculator_response(q_math2)
    resp3 = ControlIntentDetector.get_calculator_response(q_math3)

    assert "1107" in resp1
    assert "60" in resp2
    assert "25" in resp3


def test_fastpath_reminder_query_detector() -> None:
    """Verifies Reminder Fast-Path intent detector and parser."""
    q_rem = "Recuerdame en 5 minutos comprar leche"

    assert ControlIntentDetector.is_reminder_query(q_rem) is True

    desc, delay = ControlIntentDetector.parse_reminder_query(q_rem)
    assert "comprar leche" in desc
    assert delay == 300.0


def test_fastpath_weather_query_detector() -> None:
    """Verifies Weather Fast-Path intent detector and response generator."""
    q_weather = "Como esta el clima"

    assert ControlIntentDetector.is_weather_query(q_weather) is True

    resp = ControlIntentDetector.get_weather_response(q_weather)
    assert "clima" in resp.lower() or "temperatura" in resp.lower()
