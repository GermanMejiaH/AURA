from __future__ import annotations

import numpy as np

from aura.audio.input import resample_pcm_to_16k_mono


def test_resample_pcm_to_16k_mono_48k_stereo() -> None:
    """Test converting 48000 Hz stereo audio to 16000 Hz mono PCM."""
    duration_sec = 1.0
    in_rate = 48000
    in_channels = 2
    num_frames = int(in_rate * duration_sec)

    # Generate a 440 Hz sine wave for channel 0 and 880 Hz for channel 1
    t = np.linspace(0, duration_sec, num_frames, endpoint=False)
    ch1 = (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)
    ch2 = (np.sin(2 * np.pi * 880 * t) * 10000).astype(np.int16)
    stereo_interleaved = np.empty((num_frames * 2,), dtype=np.int16)
    stereo_interleaved[0::2] = ch1
    stereo_interleaved[1::2] = ch2

    pcm_48k = stereo_interleaved.tobytes()

    # Resample to 16000 Hz mono
    resampled_pcm = resample_pcm_to_16k_mono(
        pcm_bytes=pcm_48k,
        in_rate=in_rate,
        in_channels=in_channels,
        target_rate=16000,
    )

    resampled_arr = np.frombuffer(resampled_pcm, dtype=np.int16)
    expected_samples = int(16000 * duration_sec)

    # Check sample count is exactly 16000 (+/- 1 due to rounding)
    assert abs(len(resampled_arr) - expected_samples) <= 1
    assert resampled_arr.dtype == np.int16
    assert np.max(np.abs(resampled_arr)) > 0


def test_resample_pcm_to_16k_mono_passthrough() -> None:
    """Test that 16000 Hz mono audio passes through unchanged in length."""
    duration_sec = 0.5
    in_rate = 16000
    in_channels = 1
    num_samples = int(in_rate * duration_sec)

    mono_data = (np.sin(np.linspace(0, 100, num_samples)) * 5000).astype(np.int16)
    pcm_16k = mono_data.tobytes()

    resampled_pcm = resample_pcm_to_16k_mono(
        pcm_bytes=pcm_16k,
        in_rate=in_rate,
        in_channels=in_channels,
        target_rate=16000,
    )

    assert len(resampled_pcm) == len(pcm_16k)
    resampled_arr = np.frombuffer(resampled_pcm, dtype=np.int16)
    np.testing.assert_array_equal(resampled_arr, mono_data)


def test_resample_empty_buffer_returns_empty() -> None:
    """Test that empty or zero rate/channels returns empty bytes safely."""
    assert resample_pcm_to_16k_mono(b"", 48000, 2) == b""
    assert resample_pcm_to_16k_mono(b"1234", 0, 1) == b""
    assert resample_pcm_to_16k_mono(b"1234", 16000, 0) == b""
