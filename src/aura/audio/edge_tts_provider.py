from __future__ import annotations

import asyncio
import io
import subprocess
from typing import TYPE_CHECKING, Any, ClassVar

from .tts import TTSProvider, TTSResult

if TYPE_CHECKING:
    from ..config import ConfigurationManager


class EdgeTTSProvider(TTSProvider):
    """Real Text-to-Speech provider using Microsoft Edge TTS (free, no GPU needed)."""

    # Spanish voices available in Edge TTS
    VOICES: ClassVar[dict[str, str]] = {
        "es-female": "es-MX-DaliaNeural",
        "es-male": "es-MX-JorgeNeural",
        "es-aura": "es-MX-DaliaNeural",
        "default": "es-MX-DaliaNeural",
    }

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> None:
        self.config = config
        default_voice = (
            config.get_typed("tts.voice", str, "es-MX-DaliaNeural")
            if config
            else "es-MX-DaliaNeural"
        )
        selected_voice = voice if voice is not None else default_voice
        self.voice = self.VOICES.get(selected_voice, selected_voice)
        self.rate = rate
        self.pitch = pitch
        self._current_process: subprocess.Popen[Any] | None = None

    def stop(self) -> None:
        """Interrupts and stops ongoing speech playback immediately."""
        if self._current_process is not None:
            try:
                self._current_process.kill()
            except Exception:
                pass
            self._current_process = None

    def synthesize(self, text: str, voice: str = "default") -> TTSResult:
        """Converts text to MP3 audio bytes using Microsoft Edge TTS."""
        import time

        from ..logging import get_logger

        logger = get_logger("EdgeTTSProvider")

        if not text.strip():
            return TTSResult(audio_bytes=b"", text=text, duration_seconds=0.0)

        voice_name = self.VOICES.get(voice, self.voice) if voice != "default" else self.voice

        try:
            t0 = time.perf_counter()
            audio_bytes, load_ms, synth_ms, save_ms = asyncio.run(
                self._synth_async(text, voice_name)
            )
            total_synth_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                f"[TTS PROFILING] load_model_ms={load_ms:.2f} synthesize_ms={synth_ms:.2f} "
                f"save_audio_ms={save_ms:.2f} total_synth_ms={total_synth_ms:.2f}"
            )
        except Exception as exc:
            logger.warning(f"EdgeTTS synthesis failed ({exc}); returning empty TTSResult.")
            return TTSResult(audio_bytes=b"", text=text, duration_seconds=0.0)

        return TTSResult(
            audio_bytes=audio_bytes,
            text=text,
            duration_seconds=max(0.1, len(text) * 0.065),
            load_model_ms=load_ms,
            synthesize_ms=synth_ms,
            save_audio_ms=save_ms,
        )

    async def _synth_async(self, text: str, voice_name: str) -> tuple[bytes, float, float, float]:
        """Async helper to generate MP3 audio with micro-timing."""
        import time

        import edge_tts

        t_load_0 = time.perf_counter()
        communicate = edge_tts.Communicate(text, voice_name, rate=self.rate, pitch=self.pitch)
        load_ms = (time.perf_counter() - t_load_0) * 1000

        t_synth_0 = time.perf_counter()
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        synth_ms = (time.perf_counter() - t_synth_0) * 1000

        t_save_0 = time.perf_counter()
        data = buf.getvalue()
        save_ms = (time.perf_counter() - t_save_0) * 1000

        return data, load_ms, synth_ms, save_ms

    def speak(self, text: str) -> None:
        """Synthesizes and plays audio directly through the system speakers."""
        result = self.synthesize(text)
        if not result.audio_bytes:
            return

        # Use fallback player (PowerShell / system media player)
        self._play_fallback(result.audio_bytes)

    def _play_fallback(self, audio_bytes: bytes) -> None:
        """Saves MP3 to temp file and plays completely for its exact duration."""
        from .output import SoundDeviceOutputProvider

        player = SoundDeviceOutputProvider()
        player.play(audio_bytes)
