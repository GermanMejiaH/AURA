from __future__ import annotations

import io
import os
import wave
from abc import ABC, abstractmethod
from typing import Any

from ..logging import get_logger
from .types import AudioData


def resample_pcm_to_16k_mono(
    pcm_bytes: bytes,
    in_rate: int,
    in_channels: int,
    target_rate: int = 16000,
) -> bytes:
    """Resamples 16-bit PCM audio bytes to 16000 Hz mono PCM bytes using numpy."""
    if not pcm_bytes or in_rate <= 0 or in_channels <= 0:
        return b""

    import numpy as np

    arr = np.frombuffer(pcm_bytes, dtype=np.int16)
    if len(arr) == 0:
        return b""

    # 1. Downmix stereo / multi-channel to mono
    if in_channels > 1:
        # Reshape to (num_samples, in_channels) and compute mean across channels
        num_frames = len(arr) // in_channels
        if num_frames > 0:
            mono_float = (
                arr[: num_frames * in_channels].reshape(num_frames, in_channels).mean(axis=1)
            )
        else:
            mono_float = arr.astype(np.float32)
    else:
        mono_float = arr.astype(np.float32)

    # 2. Resample from in_rate to target_rate if different
    if in_rate != target_rate and len(mono_float) > 0:
        num_target_samples = round(len(mono_float) * target_rate / in_rate)
        if num_target_samples > 0:
            x_old = np.linspace(0, 1, len(mono_float), endpoint=False)
            x_new = np.linspace(0, 1, num_target_samples, endpoint=False)
            resampled_float = np.interp(x_new, x_old, mono_float)
        else:
            resampled_float = mono_float
    else:
        resampled_float = mono_float

    resampled_int16 = np.clip(resampled_float, -32768, 32767).astype(np.int16)
    return resampled_int16.tobytes()


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
    """Real audio input provider for Windows/desktop using sounddevice.

    Supports dynamic device resolution by name substring, automatic hardware sample rate
    fallback (e.g. 48000 Hz for Logitech C920), and resampling to 16 kHz mono AudioData.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        config: Any | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.config = config
        self._stream: Any = None
        self._frames: list[Any] = []
        self._capturing = False
        self._active_device: int | str | None = None
        self._actual_sample_rate = sample_rate
        self._actual_channels = channels

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

    def resolve_device_id(self, device: int | str | None = None) -> int | str | None:
        """Resolves device parameter to PortAudio device ID."""
        target_dev = device
        if target_dev is None:
            target_dev = os.environ.get("AURA_AUDIO_INPUT_DEVICE")
        if target_dev is None and self.config is not None:
            cfg_val = self.config.get("audio.input_device", "")
            if cfg_val:
                target_dev = cfg_val

        if target_dev is None or target_dev == "":
            return None

        if isinstance(target_dev, int):
            return target_dev

        dev_str = str(target_dev).strip()
        if dev_str.isdigit():
            return int(dev_str)

        # Search by name substring
        try:
            import sounddevice as sd

            devices = sd.query_devices()
            dev_str_lower = dev_str.lower()
            for idx, d in enumerate(devices):
                if d.get("max_input_channels", 0) > 0:
                    d_name = str(d.get("name", "")).lower()
                    if dev_str_lower in d_name:
                        logger = get_logger("SoundDeviceInputProvider")
                        logger.info(
                            f"Resolved audio input device '{target_dev}' -> index {idx} "
                            f"({d.get('name')})"
                        )
                        return idx
        except Exception as exc:
            logger = get_logger("SoundDeviceInputProvider")
            logger.warning(f"Error querying audio devices for '{target_dev}': {exc}")

        return target_dev

    def start_capture(self, device: int | str | None = None) -> None:
        if self._capturing:
            logger = get_logger("SoundDeviceInputProvider")
            logger.warning("Capture already active; stopping previous capture first.")
            self.stop_capture()

        import sounddevice as sd

        logger = get_logger("SoundDeviceInputProvider")
        self._frames = []
        resolved_device = self.resolve_device_id(device)
        self._active_device = resolved_device

        def callback(indata: Any, frames_count: int, time_info: Any, status: Any) -> None:
            if status and logger:
                logger.debug(f"Audio stream status: {status}")
            self._frames.append(indata.copy())

        # Determine native device parameters as fallback
        native_rate = 48000
        native_channels = self.channels
        if resolved_device is not None:
            try:
                info = sd.query_devices(resolved_device, "input")
                native_rate = int(info.get("default_samplerate", 48000))
                native_channels = int(info.get("max_input_channels", self.channels))
            except Exception:
                pass

        # Attempt 1: Try capturing at requested target sample_rate (16000 Hz)
        direct_success = False
        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=resolved_device,
                callback=callback,
            )
            self._stream.start()
            self._capturing = True
            self._actual_sample_rate = self.sample_rate
            self._actual_channels = self.channels
            logger.info(
                f"Audio capture started directly [sample_rate={self.sample_rate}, "
                f"device={resolved_device}]"
            )
            direct_success = True
        except Exception as exc:
            logger.warning(
                f"Direct 16 kHz capture failed on device '{resolved_device}' ({exc}). "
                f"Attempting fallback [rate={native_rate}, channels={native_channels}]..."
            )

        if direct_success:
            return

        # Attempt 2: Fallback to capturing at native rate and channels
        try:
            self._stream = sd.InputStream(
                samplerate=native_rate,
                channels=native_channels,
                dtype="int16",
                device=resolved_device,
                callback=callback,
            )
            self._stream.start()
            self._capturing = True
            self._actual_sample_rate = native_rate
            self._actual_channels = native_channels
            logger.info(
                f"Audio capture started at native hardware parameters [sample_rate={native_rate}, "
                f"channels={native_channels}, device={resolved_device}]"
            )
        except Exception as exc2:
            self._capturing = False
            self._stream = None
            logger.error(f"Failed to start audio capture even at native rate: {exc2}")
            raise

    def stop_capture(self) -> AudioData:
        logger = get_logger("SoundDeviceInputProvider")
        if not self._capturing or self._stream is None:
            logger.warning("stop_capture called while not capturing.")
            return AudioData(
                raw_data=b"",
                sample_rate=self.sample_rate,
                channels=1,
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
                channels=1,
                sample_format="int16",
                duration_seconds=0.0,
            )

        import numpy as np

        full_array = np.concatenate(self._frames, axis=0)
        pcm_bytes = full_array.tobytes()

        # Resample to 16 kHz mono if captured at different rate/channels
        if self._actual_sample_rate != 16000 or self._actual_channels != 1:
            logger.info(
                f"Resampling captured audio: {self._actual_sample_rate} Hz "
                f"({self._actual_channels}ch) -> 16000 Hz (1ch mono)"
            )
            final_pcm = resample_pcm_to_16k_mono(
                pcm_bytes=pcm_bytes,
                in_rate=self._actual_sample_rate,
                in_channels=self._actual_channels,
                target_rate=16000,
            )
        else:
            final_pcm = pcm_bytes

        # Wrap resampled 16 kHz mono in 16-bit PCM WAV container
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(final_pcm)

        wav_bytes = buf.getvalue()
        bytes_per_sample = 2  # 16-bit mono
        duration = len(final_pcm) / (16000 * bytes_per_sample) if len(final_pcm) > 0 else 0.0

        logger.info(
            f"Audio capture stopped and resampled to 16 kHz mono. Total duration={duration:.2f}s"
        )
        return AudioData(
            raw_data=wav_bytes,
            sample_rate=16000,
            channels=1,
            sample_format="int16",
            duration_seconds=duration,
        )

    def is_capturing(self) -> bool:
        return self._capturing

    def close(self) -> None:
        if self._capturing:
            self.stop_capture()
