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
        if not text.strip():
            return TTSResult(audio_bytes=b"", text=text, duration_seconds=0.0)

        voice_name = self.VOICES.get(voice, self.voice) if voice != "default" else self.voice

        try:
            audio_bytes = asyncio.run(self._synth_async(text, voice_name))
        except Exception as exc:
            from ..logging import get_logger

            logger = get_logger("EdgeTTSProvider")
            logger.warning(f"EdgeTTS synthesis failed ({exc}); returning empty TTSResult.")
            return TTSResult(audio_bytes=b"", text=text, duration_seconds=0.0)

        return TTSResult(
            audio_bytes=audio_bytes,
            text=text,
            duration_seconds=max(0.1, len(text) * 0.065),
        )

    async def _synth_async(self, text: str, voice_name: str) -> bytes:
        """Async helper to generate MP3 audio from Edge TTS."""
        import edge_tts

        buf = io.BytesIO()
        communicate = edge_tts.Communicate(text, voice_name, rate=self.rate, pitch=self.pitch)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    def speak(self, text: str) -> None:
        """Synthesizes and plays audio directly through the system speakers."""
        result = self.synthesize(text)
        if not result.audio_bytes:
            return

        # Use fallback player (PowerShell / system media player)
        self._play_fallback(result.audio_bytes)

    def _play_fallback(self, audio_bytes: bytes) -> None:
        """Saves MP3 to temp file and plays completely for its exact duration."""
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
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
            "  Start-Sleep -s 120 "
            "} ; "
            "$m.Close()"
        )

        try:
            self._current_process = subprocess.Popen(
                ["powershell", "-c", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._current_process.wait()
        except Exception:
            pass
        finally:
            self._current_process = None
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
