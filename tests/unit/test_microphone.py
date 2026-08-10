from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from aura.audio import MicrophoneRecorder


def test_microphone_recorder_fixed_duration():
    recorder = MicrophoneRecorder(sample_rate=16000)

    fake_data = np.zeros((16000, 1), dtype=np.int16)

    with patch("sounddevice.rec", return_value=fake_data), patch("sounddevice.wait"):
        audio_bytes = recorder.record_bytes(duration_sec=1.0)
        assert len(audio_bytes) > 44  # WAV header is 44 bytes
        assert audio_bytes.startswith(b"RIFF")


def test_microphone_recorder_until_silence():
    recorder = MicrophoneRecorder(sample_rate=16000)

    fake_chunk = np.ones((1600, 1), dtype=np.int16) * 500
    mock_stream = MagicMock()
    mock_stream.__enter__.return_value = mock_stream
    mock_stream.read.return_value = (fake_chunk, False)

    with patch("sounddevice.InputStream", return_value=mock_stream):
        audio_bytes = recorder.record_until_silence(max_duration_sec=0.3, silence_sec=0.2)
        assert len(audio_bytes) > 44
        assert audio_bytes.startswith(b"RIFF")
