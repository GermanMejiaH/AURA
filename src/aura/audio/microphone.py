from __future__ import annotations

import io
import wave
from typing import Any

from .silence import SilenceDetector


class MicrophoneRecorder:
    """Captures real-time PCM audio from default microphone."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.silence_detector = SilenceDetector()

    def record_bytes(self, duration_sec: float = 3.0) -> bytes:
        """Records microphone input for a fixed duration and returns 16-bit mono WAV bytes."""
        import sounddevice as sd  # type: ignore[import-untyped]

        recording = sd.rec(
            int(duration_sec * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
        )
        sd.wait()

        # Convert numpy array to 16-bit PCM WAV bytes
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 2 bytes for int16
            wf.setframerate(self.sample_rate)
            wf.writeframes(recording.tobytes())

        return buf.getvalue()

    def record_until_silence(
        self,
        max_duration_sec: float = 10.0,
        silence_sec: float = 1.2,
        energy_threshold: float = 300.0,
    ) -> bytes:
        """Records microphone input until speech ends (detected silence) or max duration reached."""
        import numpy as np
        import sounddevice as sd

        chunk_duration = 0.1  # 100ms chunks
        chunk_samples = int(chunk_duration * self.sample_rate)
        frames: list[np.ndarray[Any, Any]] = []

        silent_chunks = 0
        max_silent_chunks = int(silence_sec / chunk_duration)
        total_chunks = int(max_duration_sec / chunk_duration)

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
        ) as stream:
            for _ in range(total_chunks):
                chunk, _ = stream.read(chunk_samples)
                frames.append(chunk)

                # Compute RMS energy of the 16-bit chunk
                rms = (
                    float(np.sqrt(np.mean(np.square(chunk.astype(np.float32)))))
                    if len(chunk) > 0
                    else 0.0
                )
                if rms < energy_threshold:
                    silent_chunks += 1
                else:
                    silent_chunks = 0

                # Stop recording if we've accumulated speech and now hit silence
                if len(frames) > 5 and silent_chunks >= max_silent_chunks:
                    self.silence_detector.process_silence_duration(
                        silent_chunks * chunk_duration
                    )
                    break

        if not frames:
            return b""

        full_audio = np.concatenate(frames, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(full_audio.tobytes())

        return buf.getvalue()
