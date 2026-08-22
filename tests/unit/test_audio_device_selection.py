from __future__ import annotations

from unittest.mock import patch

from aura.audio.input import SoundDeviceInputProvider
from aura.config import ConfigurationManager


def test_resolve_device_by_name_substring() -> None:
    """Test resolving input device ID by device name substring (e.g. 'C920')."""
    provider = SoundDeviceInputProvider()

    mock_devices = [
        {"name": "Speakers (Realtek Audio)", "max_input_channels": 0},
        {"name": "Microphone (HD Pro Webcam C920)", "max_input_channels": 2},
        {"name": "Realtek High Definition Audio", "max_input_channels": 2},
    ]

    with patch("sounddevice.query_devices", return_value=mock_devices):
        resolved_c920 = provider.resolve_device_id("C920")
        assert resolved_c920 == 1

        resolved_webcam = provider.resolve_device_id("Microphone (HD Pro Webcam C920)")
        assert resolved_webcam == 1

        resolved_realtek = provider.resolve_device_id("realtek")
        assert resolved_realtek == 2


def test_resolve_device_by_integer_index() -> None:
    """Test resolving input device by direct integer index or index string."""
    provider = SoundDeviceInputProvider()
    assert provider.resolve_device_id(23) == 23
    assert provider.resolve_device_id("23") == 23


def test_resolve_device_from_config() -> None:
    """Test resolving input device from ConfigurationManager 'audio.input_device'."""
    config = ConfigurationManager()
    config.set("audio.input_device", "C920")
    provider = SoundDeviceInputProvider(config=config)

    mock_devices = [
        {"name": "Microphone (HD Pro Webcam C920)", "max_input_channels": 2},
    ]

    with patch("sounddevice.query_devices", return_value=mock_devices):
        resolved = provider.resolve_device_id(None)
        assert resolved == 0
