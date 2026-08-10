from __future__ import annotations

from unittest.mock import MagicMock, patch

from aura.audio.input import MockAudioInputProvider, SoundDeviceInputProvider
from aura.audio.output import MockAudioOutputProvider, SoundDeviceOutputProvider
from aura.audio.types import AudioData


def test_mock_audio_input_provider_lifecycle() -> None:
    provider = MockAudioInputProvider(mock_text="Prueba de audio", mock_duration=2.0)
    assert not provider.is_capturing()

    provider.start_capture()
    assert provider.is_capturing()

    audio = provider.stop_capture()
    assert not provider.is_capturing()
    assert isinstance(audio, AudioData)
    assert audio.text_hint == "Prueba de audio"
    assert audio.duration_seconds == 2.0


def test_sounddevice_input_provider_double_start_and_cleanup() -> None:
    provider = SoundDeviceInputProvider(sample_rate=16000, channels=1)
    assert not provider.is_capturing()

    mock_stream = MagicMock()
    with patch("sounddevice.InputStream", return_value=mock_stream):
        provider.start_capture()
        assert provider.is_capturing()
        mock_stream.start.assert_called_once()

        # Double start should safely stop and restart
        provider.start_capture()
        assert provider.is_capturing()
        assert mock_stream.stop.called

        audio = provider.stop_capture()
        assert not provider.is_capturing()
        assert isinstance(audio, AudioData)
        assert audio.sample_rate == 16000


def test_mock_audio_output_provider_play_and_stop() -> None:
    provider = MockAudioOutputProvider()
    assert not provider.is_playing()

    test_bytes = b"RIFF\x00\x00\x00\x00WAVEfmt "
    success = provider.play(test_bytes)
    assert success
    assert provider.last_played_bytes == test_bytes

    provider.stop()
    assert not provider.is_playing()


def test_sounddevice_output_provider_wav_play_mock() -> None:
    provider = SoundDeviceOutputProvider()

    with (
        patch("wave.open") as mock_wave_open,
        patch("sounddevice.play") as mock_play,
        patch("sounddevice.wait"),
    ):
        mock_wf = MagicMock()
        mock_wf.getframerate.return_value = 16000
        mock_wf.getnchannels.return_value = 1
        mock_wf.getsampwidth.return_value = 2
        mock_wf.getnframes.return_value = 100
        mock_wf.readframes.return_value = b"\x00\x00" * 100
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        wav_header = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00"
        success = provider.play(wav_header)
        assert success
        mock_play.assert_called_once()
