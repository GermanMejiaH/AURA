from __future__ import annotations

import io
import wave
from abc import ABC, abstractmethod
from typing import Any

from ..logging import get_logger
from .types import AudioData


class AudioInputProvider(ABC):
    """Abstract interface for audio input capture (microphones, file input, audio streams)."""

    @abstractmethod
    def start_capture(self, device: int | str | None = None) -> None:
        """Start capturing audio from the specified device or default input."""
        ...

    @abstractmethod
    def stop_capture(self) -> AudioData:
        """Stop capturing audio and return captured AudioData."""
        ...

    @abstractmethod
    def is_capturing(self) -> bool:
        """Returns True if audio capture is active."""
        ...

    def list_devices(self) -> list[dict[str, Any]]:
        """Lists available input audio devices."""
        return []

    def close(self) -> None:
        """Release underlying hardware resources safely."""
        pass


class MockAudioInputProvider(AudioInputProvider):
    """Mock audio input provider for testing and environments without hardware."""

    def __init__(
        self,
        mock_text: str = "Hola AURA, ¿cuál es tu estado?",
        mock_duration: float = 1.5,
    ) -> None:
        self.mock_text = mock_text
        self.mock_duration = mock_duration
        self._capturing = False

    def start_capture(self, device: int | str | None = None) -> None:
        self._capturing = True

    def stop_capture(self) -> AudioData:
        self._capturing = False
        return AudioData.create_mock(text=self.mock_text, duration=self.mock_duration)

    def is_capturing(self) -> bool:
        return self._capturing


class SoundDeviceInputProvider(AudioInputProvider):
    """Real audio input provider for Windows/desktop using sounddevice."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream: Any = None
        self._frames: list[Any] = []
        self._capturing = False
        self._active_device: int | str | None = None

    def list_devices(self) -> list[dict[str, Any]]:
        input_devs: list[dict[str, Any]] = []
        try:
            import sounddevice as sd  # type: ignore[import-untyped]

            devices = sd.query_devices()
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    input_devs.append(
                        {
                            "id": idx,
                            "name": dev.get("name", f"Input Device {idx}"),
                            "channels": dev.get("max_input_channels", 1),
                            "default_samplerate": dev.get("default_samplerate", 44100),
                        }
                    )
        except Exception as exc:
            logger = get_logger("SoundDeviceInputProvider")
            logger.warning(f"Failed to list input audio devices: {exc}")
            return []
        return input_devs

    def start_capture(self, device: int | str | None = None) -> None:
        if self._capturing:
            logger = get_logger("SoundDeviceInputProvider")
            logger.warning("Capture already active; stopping previous capture first.")
            self.stop_capture()

        import sounddevice as sd

        logger = get_logger("SoundDeviceInputProvider")
        self._frames = []
        self._active_device = device

        def callback(indata: Any, frames_count: int, time_info: Any, status: Any) -> None:
            if status and logger:
                logger.debug(f"Audio stream status: {status}")
            self._frames.append(indata.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=device,
                callback=callback,
            )
            self._stream.start()
            self._capturing = True
            logger.info(f"Audio capture started [sample_rate={self.sample_rate}, device={device}]")
        except Exception as exc:
            self._capturing = False
            self._stream = None
            logger.error(f"Failed to start audio capture: {exc}")
            raise

    def stop_capture(self) -> AudioData:
        logger = get_logger("SoundDeviceInputProvider")
        if not self._capturing or self._stream is None:
            logger.warning("stop_capture called while not capturing.")
            return AudioData(
                raw_data=b"",
                sample_rate=self.sample_rate,
                channels=self.channels,
                sample_format="int16",
                duration_seconds=0.0,
            )

        try:
            self._stream.stop()
            self._stream.close()
        except Exception as exc:
            logger.warning(f"Exception stopping audio stream: {exc}")
        finally:
            self._stream = None
            self._capturing = False

        if not self._frames:
            return AudioData(
                raw_data=b"",
                sample_rate=self.sample_rate,
                channels=self.channels,
                sample_format="int16",
                duration_seconds=0.0,
            )

        import numpy as np

        full_array = np.concatenate(self._frames, axis=0)
        pcm_bytes = full_array.tobytes()

        # Wrap in 16-bit PCM WAV container
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)

        wav_bytes = buf.getvalue()
        bytes_per_sample = 2 * self.channels
        if bytes_per_sample > 0 and self.sample_rate > 0:
            duration = len(pcm_bytes) / (self.sample_rate * bytes_per_sample)
        else:
            duration = 0.0

        logger.info(f"Audio capture stopped. Total duration={duration:.2f}s")
        return AudioData(
            raw_data=wav_bytes,
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_format="int16",
            duration_seconds=duration,
        )

    def is_capturing(self) -> bool:
        return self._capturing

    def close(self) -> None:
        if self._capturing:
            self.stop_capture()
