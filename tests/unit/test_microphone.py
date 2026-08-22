from __future__ import annotations

import io
import wave
from unittest.mock import MagicMock, patch

import numpy as np

from aura.audio import MicrophoneRecorder
from aura.config import ConfigurationManager


def test_microphone_recorder_fixed_duration() -> None:
    recorder = MicrophoneRecorder(sample_rate=16000)
    fake_data = np.zeros((16000, 1), dtype=np.int16)

    with patch("sounddevice.rec", return_value=fake_data), patch("sounddevice.wait"):
        audio_bytes = recorder.record_bytes(duration_sec=1.0)
        assert len(audio_bytes) > 44  # WAV header is 44 bytes
        assert audio_bytes.startswith(b"RIFF")


def test_microphone_recorder_until_silence() -> None:
    recorder = MicrophoneRecorder(sample_rate=16000)

    fake_chunk = np.ones((1600, 1), dtype=np.int16) * 500
    mock_stream = MagicMock()
    mock_stream.__enter__.return_value = mock_stream
    mock_stream.read.return_value = (fake_chunk, False)

    with patch("sounddevice.InputStream", return_value=mock_stream):
        audio_bytes = recorder.record_until_silence(max_duration_sec=0.3, silence_sec=0.2)
        assert len(audio_bytes) > 44
        assert audio_bytes.startswith(b"RIFF")


def test_microphone_recorder_resolve_device_c920() -> None:
    """Test resolving 'C920' to device index of Logitech C920 camera."""
    mock_devices = [
        {"name": "Speakers (Realtek Audio)", "max_input_channels": 0},
        {"name": "Microphone (G433 Gaming Headset)", "max_input_channels": 1},
        {"name": "Microphone (HD Pro Webcam C920)", "max_input_channels": 2},
    ]

    recorder = MicrophoneRecorder()
    with patch("sounddevice.query_devices", return_value=mock_devices):
        resolved = recorder.resolve_device_id("C920")
        assert resolved == 2


def test_microphone_recorder_case_insensitive_resolve() -> None:
    """Test resolving device name substring case-insensitively."""
    mock_devices = [
        {"name": "Microphone (HD Pro Webcam C920)", "max_input_channels": 2},
    ]

    recorder = MicrophoneRecorder()
    with patch("sounddevice.query_devices", return_value=mock_devices):
        assert recorder.resolve_device_id("c920") == 0
        assert recorder.resolve_device_id("WEBCAM") == 0
        assert recorder.resolve_device_id("hd pro") == 0


def test_microphone_recorder_numeric_index() -> None:
    """Test compatibility with direct numeric integer or string index."""
    recorder = MicrophoneRecorder()
    assert recorder.resolve_device_id(3) == 3
    assert recorder.resolve_device_id("3") == 3


def test_microphone_recorder_produces_16k_mono_wav() -> None:
    """Test that record_bytes outputs a valid WAV container with 16 kHz mono framerate."""
    recorder = MicrophoneRecorder(device="C920")
    fake_data = np.zeros((48000, 2), dtype=np.int16)

    # Force fallback simulation to 48000 Hz stereo
    def rec_side_effect(*args, **kwargs):
        if kwargs.get("samplerate") == 16000:
            raise RuntimeError("Invalid sample rate")
        return fake_data

    mock_dev_info = {
        "name": "Microphone (HD Pro Webcam C920)",
        "default_samplerate": 48000.0,
        "max_input_channels": 2,
    }

    with (
        patch("sounddevice.query_devices", return_value=mock_dev_info),
        patch("sounddevice.rec", side_effect=rec_side_effect),
        patch("sounddevice.wait"),
    ):
        wav_bytes = recorder.record_bytes(duration_sec=1.0)
        assert wav_bytes.startswith(b"RIFF")

        # Verify WAV container properties
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            assert wf.getframerate() == 16000
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2


def test_converse_cli_acquires_configured_device() -> None:
    """Test that _handle_converse acquires audio.input_device from ConfigurationManager."""
    from aura.cli import _handle_converse

    config = ConfigurationManager()
    config.set("audio.input_device", "C920")

    mock_aura = MagicMock()
    mock_aura.config = config
    mock_aura.module_manager = None

    with (
        patch("aura.audio.MicrophoneRecorder") as mock_recorder_cls,
        patch("aura.audio.FasterWhisperSTTProvider"),
        patch("aura.audio.EdgeTTSProvider"),
        patch("aura.cognition.OpenAILLMProvider"),
    ):
        mock_rec_inst = MagicMock()
        mock_rec_inst.record_bytes.return_value = b""
        mock_recorder_cls.return_value = mock_rec_inst

        # Run 1 round of converse loop
        _handle_converse(mock_aura, arg="1")

        mock_recorder_cls.assert_called_once_with(device="C920")


def test_normalize_pcm_gain() -> None:
    """Unit tests for normalize_pcm_gain under various signal amplitude conditions."""
    from aura.audio.microphone import normalize_pcm_gain

    # 1. Empty audio
    assert normalize_pcm_gain(b"") == b""

    # 2. Silent audio (peak < 300) -> unchanged
    silent_pcm = np.array([10, -15, 20, -5], dtype=np.int16).tobytes()
    assert normalize_pcm_gain(silent_pcm) == silent_pcm

    # 3. Already loud audio (peak >= 24000) -> unchanged
    loud_pcm = np.array([25000, -26000, 10000], dtype=np.int16).tobytes()
    assert normalize_pcm_gain(loud_pcm) == loud_pcm

    # 4. Low amplitude speech (peak = 1000) -> normalized with max_gain=3.0 -> peak=3000
    low_speech = np.array([1000, -500, 800], dtype=np.int16)
    norm_bytes = normalize_pcm_gain(low_speech.tobytes(), target_peak=24000.0, max_gain=3.0)
    norm_arr = np.frombuffer(norm_bytes, dtype=np.int16)
    assert np.max(np.abs(norm_arr)) == 3000

    # 5. Audio near clipping limit -> scaled safely without clipping
    saturating = np.array([12000, -12000, 6000], dtype=np.int16)
    sat_bytes = normalize_pcm_gain(saturating.tobytes(), target_peak=24000.0, max_gain=3.0)
    sat_arr = np.frombuffer(sat_bytes, dtype=np.int16)
    assert np.max(np.abs(sat_arr)) == 24000
    assert np.all(sat_arr >= -32768) and np.all(sat_arr <= 32767)
