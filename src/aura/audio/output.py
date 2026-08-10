from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from abc import ABC, abstractmethod
from typing import Any

from ..logging import get_logger
from .types import AudioData


class AudioOutputProvider(ABC):
    """Abstract interface for audio playback (speakers, headphone jacks, virtual audio)."""

    @abstractmethod
    def play(self, audio: AudioData | bytes) -> bool:
        """Plays audio data through system speakers. Returns True if successful."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Interrupts and stops ongoing speech playback immediately."""
        ...

    @abstractmethod
    def is_playing(self) -> bool:
        """Returns True if audio playback is currently active."""
        ...

    def list_devices(self) -> list[dict[str, Any]]:
        """Lists available output audio devices."""
        return []

    def close(self) -> None:
        """Release underlying hardware resources safely."""
        pass


class MockAudioOutputProvider(AudioOutputProvider):
    """Mock audio output provider for testing and environments without speakers."""

    def __init__(self) -> None:
        self.last_played_bytes: bytes | None = None
        self._playing = False

    def play(self, audio: AudioData | bytes) -> bool:
        raw_bytes = audio.raw_data if isinstance(audio, AudioData) else audio
        self.last_played_bytes = raw_bytes
        self._playing = False
        return True

    def stop(self) -> None:
        self._playing = False

    def is_playing(self) -> bool:
        return self._playing


class SoundDeviceOutputProvider(AudioOutputProvider):
    """Real audio output provider for Windows using sounddevice and system media player fallback."""

    def __init__(self) -> None:
        self._playing = False
        self._process: subprocess.Popen[Any] | None = None
        self._lock = threading.RLock()

    def list_devices(self) -> list[dict[str, Any]]:
        output_devs: list[dict[str, Any]] = []
        try:
            import sounddevice as sd  # type: ignore[import-untyped]

            devices = sd.query_devices()
            for idx, dev in enumerate(devices):
                if dev.get("max_output_channels", 0) > 0:
                    output_devs.append(
                        {
                            "id": idx,
                            "name": dev.get("name", f"Output Device {idx}"),
                            "channels": dev.get("max_output_channels", 2),
                            "default_samplerate": dev.get("default_samplerate", 44100),
                        }
                    )
        except Exception as exc:
            logger = get_logger("SoundDeviceOutputProvider")
            logger.warning(f"Failed to list output audio devices: {exc}")
            return []
        return output_devs

    def play(self, audio: AudioData | bytes) -> bool:
        raw_bytes = audio.raw_data if isinstance(audio, AudioData) else audio
        if not raw_bytes:
            return False

        logger = get_logger("SoundDeviceOutputProvider")

        with self._lock:
            if self._playing:
                self.stop()
            self._playing = True

        # Check if raw_bytes starts with RIFF (WAV) or ID3/MP3 header
        is_wav = raw_bytes.startswith(b"RIFF")
        is_mp3 = (
            raw_bytes.startswith(b"ID3")
            or raw_bytes.startswith(b"\xff\xfb")
            or raw_bytes.startswith(b"\xff\xf3")
        )

        try:
            if is_wav:
                played = self._play_wav_bytes(raw_bytes)
            elif is_mp3 or len(raw_bytes) > 0:
                played = self._play_mp3_bytes(raw_bytes)
            else:
                played = False
        except Exception as exc:
            logger.error(f"Playback failed: {exc}")
            played = False
        finally:
            with self._lock:
                self._playing = False
        return played

    def stop(self) -> None:
        with self._lock:
            if self._process is not None:
                try:
                    self._process.kill()
                except Exception:
                    pass
                self._process = None
            self._playing = False

    def is_playing(self) -> bool:
        with self._lock:
            return self._playing

    def close(self) -> None:
        self.stop()

    def _play_wav_bytes(self, wav_bytes: bytes) -> bool:
        logger = get_logger("SoundDeviceOutputProvider")
        try:
            import io
            import wave

            import numpy as np
            import sounddevice as sd

            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                framerate = wf.getframerate()
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                raw_frames = wf.readframes(wf.getnframes())

            dtype = "int16" if sampwidth == 2 else "uint8"
            audio_array: Any = np.frombuffer(raw_frames, dtype=dtype)
            if nchannels > 1:
                audio_array = audio_array.reshape(-1, nchannels)

            sd.play(audio_array, framerate)
            sd.wait()
            played = True
        except Exception:
            logger.debug("wave/sounddevice play failed, falling back to temp file player.")
            played = self._play_mp3_bytes(wav_bytes, suffix=".wav")
        return played

    def _play_mp3_bytes(self, audio_bytes: bytes, suffix: str = ".mp3") -> bool:
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            ps_script = (
                "Add-Type -AssemblyName presentationCore ; "
                f"$m=New-Object System.Windows.Media.MediaPlayer ; "
                f"$m.Open([uri]'{tmp_path}') ; "
                f"$m.Play() ; "
                "$w=0 ; "
                "while (-not $m.NaturalDuration.HasTimeSpan -and $w -lt 40) { "
                "  Start-Sleep -m 100 ; $w++ "
                "} ; "
                "if ($m.NaturalDuration.HasTimeSpan) { "
                "  $ms = [int]$m.NaturalDuration.TimeSpan.TotalMilliseconds ; "
                "  Start-Sleep -m ($ms + 300) "
                "} else { "
                "  Start-Sleep -s 5 "
                "} ; "
                "$m.Close()"
            )

            with self._lock:
                self._process = subprocess.Popen(
                    ["powershell", "-c", ps_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            if self._process is not None:
                self._process.wait()

            played = True
        except Exception as exc:
            logger = get_logger("SoundDeviceOutputProvider")
            logger.warning(f"Fallback audio playback failed: {exc}")
            played = False
        finally:
            with self._lock:
                self._process = None
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        return played
