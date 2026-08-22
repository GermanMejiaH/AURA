from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from aura.audio.input import SoundDeviceInputProvider


def test_start_capture_direct_16k_success() -> None:
    """Test successful 16 kHz stream capture initialization without fallback."""
    provider = SoundDeviceInputProvider(sample_rate=16000)

    mock_stream = MagicMock()
    with patch("sounddevice.InputStream", return_value=mock_stream) as mock_input:
        provider.start_capture(device=None)
        assert provider.is_capturing() is True
        assert provider._actual_sample_rate == 16000
        mock_input.assert_called_once()


def test_start_capture_fallback_to_native_48k_on_portaudio_error() -> None:
    """Test automatic fallback to native 48000 Hz device sample rate when 16 kHz fails."""
    provider = SoundDeviceInputProvider(sample_rate=16000)

    mock_dev_info = {
        "name": "Microphone (HD Pro Webcam C920)",
        "default_samplerate": 48000.0,
        "max_input_channels": 2,
    }

    mock_stream = MagicMock()

    def stream_side_effect(*args, **kwargs):
        if kwargs.get("samplerate") == 16000:
            raise RuntimeError("Invalid sample rate [PaErrorCode -9997]")
        return mock_stream

    with (
        patch("sounddevice.query_devices", return_value=mock_dev_info),
        patch("sounddevice.InputStream", side_effect=stream_side_effect) as mock_input,
    ):
        provider.start_capture(device="C920")

        assert provider.is_capturing() is True
        assert provider._actual_sample_rate == 48000
        assert provider._actual_channels == 2
        assert mock_input.call_count == 2


def test_stop_capture_resamples_48k_native_frames_to_16k_mono_audiodata() -> None:
    """Test stop_capture converting 48 kHz stereo captured frames into 16 kHz mono AudioData."""
    provider = SoundDeviceInputProvider(sample_rate=16000)
    provider._capturing = True
    provider._actual_sample_rate = 48000
    provider._actual_channels = 2
    mock_stream = MagicMock()
    provider._stream = mock_stream

    # Create 0.5s of 48 kHz stereo dummy frames (24000 frames x 2 = 48000 int16 samples)
    dummy_frame = np.ones((24000, 2), dtype=np.int16) * 1000
    provider._frames = [dummy_frame]

    audio_data = provider.stop_capture()

    assert audio_data.sample_rate == 16000
    assert audio_data.channels == 1
    assert audio_data.duration_seconds > 0.4
    assert len(audio_data.raw_data) > 44  # Valid WAV header + resampled PCM
