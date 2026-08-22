from __future__ import annotations

import io
import os
import wave
from typing import Any

from .input import resample_pcm_to_16k_mono
from .silence import SilenceDetector


def normalize_pcm_gain(
    pcm_bytes: bytes,
    target_peak: float = 24000.0,
    max_gain: float = 3.0,
    min_speech_peak: float = 300.0,
) -> bytes:
    """Applies moderate, controlled gain normalization to 16-bit PCM mono audio,
    avoiding clipping."""
    import numpy as np

    if not pcm_bytes:
        return pcm_bytes

    arr = np.frombuffer(pcm_bytes, dtype=np.int16)
    if len(arr) == 0:
        return pcm_bytes

    current_max = float(np.max(np.abs(arr)))
    if current_max < min_speech_peak or current_max >= target_peak:
        # Don't amplify silence or audio that's already sufficiently loud
        return pcm_bytes

    gain = min(target_peak / current_max, max_gain)
    amplified = np.clip(arr.astype(np.float32) * gain, -32768, 32767).astype(np.int16)
    return bytes(amplified.tobytes())


class MicrophoneRecorder:
    """Captures real-time PCM audio from microphone with fallback and resampling."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device: int | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device
        self.silence_detector = SilenceDetector()

    def resolve_device_id(self, device: int | str | None = None) -> int | str | None:
        """Resolves device parameter (index, name substring, config/env) to PortAudio ID."""
        target_dev = device if device is not None else self.device
        if target_dev is None or target_dev == "":
            target_dev = os.environ.get("AURA_AUDIO_INPUT_DEVICE")

        if target_dev is None or target_dev == "":
            return None

        if isinstance(target_dev, int):
            return target_dev

        dev_str = str(target_dev).strip()
        if dev_str.isdigit():
            return int(dev_str)

        # Search by name substring (case-insensitive)
        try:
            import sounddevice as sd  # type: ignore[import-untyped]

            devices = sd.query_devices()
            dev_str_lower = dev_str.lower()
            for idx, d in enumerate(devices):
                if d.get("max_input_channels", 0) > 0:
                    d_name = str(d.get("name", "")).lower()
                    if dev_str_lower in d_name:
                        return idx
        except Exception:
            pass

        return target_dev

    def record_bytes(self, duration_sec: float = 3.0) -> bytes:
        """Records microphone input for a fixed duration and returns 16-bit 16kHz mono WAV bytes."""
        import sounddevice as sd

        dev_id = self.resolve_device_id(self.device)
        actual_rate = self.sample_rate
        actual_channels = self.channels

        native_rate = 48000
        native_channels = self.channels
        if dev_id is not None:
            try:
                info = sd.query_devices(dev_id, "input")
                native_rate = int(info.get("default_samplerate", 48000))
                native_channels = int(info.get("max_input_channels", self.channels))
            except Exception:
                pass

        try:
            recording = sd.rec(
                int(duration_sec * self.sample_rate),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=dev_id,
            )
            sd.wait()
        except Exception:
            # Fallback to native hardware rate & channels if direct 16000 Hz fails
            actual_rate = native_rate
            actual_channels = native_channels
            recording = sd.rec(
                int(duration_sec * actual_rate),
                samplerate=actual_rate,
                channels=actual_channels,
                dtype="int16",
                device=dev_id,
            )
            sd.wait()

        pcm_bytes = recording.tobytes()

        if actual_rate != 16000 or actual_channels != 1:
            final_pcm = resample_pcm_to_16k_mono(
                pcm_bytes=pcm_bytes,
                in_rate=actual_rate,
                in_channels=actual_channels,
                target_rate=16000,
            )
        else:
            final_pcm = pcm_bytes

        final_pcm = normalize_pcm_gain(final_pcm)

        # Convert numpy array to 16-bit PCM WAV bytes at 16000 Hz mono
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 2 bytes for int16
            wf.setframerate(16000)
            wf.writeframes(final_pcm)

        return buf.getvalue()

    def record_until_silence(
        self,
        max_duration_sec: float = 10.0,
        silence_sec: float = 1.2,
        energy_threshold: float = 120.0,
    ) -> bytes:
        """Records microphone input until speech ends (detected silence) or max duration reached."""
        import numpy as np
        import sounddevice as sd

        dev_id = self.resolve_device_id(self.device)
        actual_rate = self.sample_rate
        actual_channels = self.channels
        chunk_duration = 0.1  # 100ms chunks

        native_rate = 48000
        native_channels = self.channels
        if dev_id is not None:
            try:
                info = sd.query_devices(dev_id, "input")
                native_rate = int(info.get("default_samplerate", 48000))
                native_channels = int(info.get("max_input_channels", self.channels))
            except Exception:
                pass

        # Try to open InputStream at requested rate or fallback to native rate
        stream = None
        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=dev_id,
            )
            stream.start()
        except Exception:
            actual_rate = native_rate
            actual_channels = native_channels
            stream = sd.InputStream(
                samplerate=actual_rate,
                channels=actual_channels,
                dtype="int16",
                device=dev_id,
            )
            stream.start()

        chunk_samples = int(chunk_duration * actual_rate)
        frames: list[np.ndarray[Any, Any]] = []
        rms_values: list[float] = []

        speech_started = False
        consecutive_speech_chunks = 0
        silent_chunks = 0
        max_silent_chunks = int(silence_sec / chunk_duration)
        total_chunks = int(max_duration_sec / chunk_duration)

        try:
            for _ in range(total_chunks):
                chunk, _ = stream.read(chunk_samples)
                frames.append(chunk)

                # Compute RMS energy of the 16-bit chunk
                rms = (
                    float(np.sqrt(np.mean(np.square(chunk.astype(np.float32)))))
                    if len(chunk) > 0
                    else 0.0
                )
                rms_values.append(rms)

                if rms >= energy_threshold:
                    consecutive_speech_chunks += 1
                    if consecutive_speech_chunks >= 2:
                        speech_started = True
                    silent_chunks = 0
                else:
                    consecutive_speech_chunks = 0
                    silent_chunks += 1

                # Stop recording only after speech started and trailing silence is reached
                if speech_started and silent_chunks >= max_silent_chunks:
                    self.silence_detector.process_silence_duration(silent_chunks * chunk_duration)
                    break
        finally:
            if stream is not None:
                stream.stop()
                stream.close()

        min_rms = min(rms_values) if rms_values else 0.0
        max_rms = max(rms_values) if rms_values else 0.0
        avg_rms = sum(rms_values) / len(rms_values) if rms_values else 0.0

        if not speech_started or not frames:
            print(
                "  [AUTO VAD] Capture returned EMPTY AUDIO (No speech detected above threshold) | "
                f"RMS stats: min={min_rms:.1f}, max={max_rms:.1f}, avg={avg_rms:.1f} | "
                f"threshold={energy_threshold}"
            )
            return b""

        print(
            f"  [AUTO VAD] Speech detected! Chunks={len(frames)} | "
            f"RMS stats: min={min_rms:.1f}, max={max_rms:.1f}, avg={avg_rms:.1f} | "
            f"threshold={energy_threshold}"
        )

        full_audio = np.concatenate(frames, axis=0)
        pcm_bytes = full_audio.tobytes()

        if actual_rate != 16000 or actual_channels != 1:
            final_pcm = resample_pcm_to_16k_mono(
                pcm_bytes=pcm_bytes,
                in_rate=actual_rate,
                in_channels=actual_channels,
                target_rate=16000,
            )
        else:
            final_pcm = pcm_bytes

        final_pcm = normalize_pcm_gain(final_pcm)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(final_pcm)

        return buf.getvalue()
