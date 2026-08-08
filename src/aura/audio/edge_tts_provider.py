from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING, ClassVar

from .tts import TTSProvider, TTSResult

if TYPE_CHECKING:
    from ..events import EventBus


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
        voice: str = "es-aura",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        event_bus: EventBus | None = None,
    ) -> None:
        self.voice = self.VOICES.get(voice, voice)
        self.rate = rate
        self.pitch = pitch
        self.event_bus = event_bus

    def synthesize(self, text: str, voice: str = "default") -> TTSResult:
        """Converts text to MP3 audio bytes using Microsoft Edge TTS."""
        if not text.strip():
            return TTSResult(audio_bytes=b"", text=text, duration_seconds=0.0)

        voice_name = self.VOICES.get(voice, self.voice)
        audio_bytes = asyncio.run(self._synth_async(text, voice_name))

        result = TTSResult(
            audio_bytes=audio_bytes,
            text=text,
            duration_seconds=len(text) * 0.065,  # ~65ms per character estimate
        )

        if self.event_bus is not None:
            from ..events import AudioPlaybackStarted, SpeechSynthesized

            self.event_bus.publish(
                SpeechSynthesized(
                    source="EdgeTTSProvider",
                    text=text,
                    audio_bytes_length=len(audio_bytes),
                )
            )
            self.event_bus.publish(AudioPlaybackStarted(source="EdgeTTSProvider", text=text))

        return result

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

        if self.event_bus is not None:
            from ..events import AudioPlaybackFinished

            self.event_bus.publish(AudioPlaybackFinished(source="EdgeTTSProvider", text=text))

    def _play_fallback(self, audio_bytes: bytes) -> None:
        """Saves MP3 to temp file and plays with system default player."""
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            # PowerShell / Windows Media Player silent playback
            subprocess.run(
                [
                    "powershell",
                    "-c",
                    f"(New-Object Media.SoundPlayer).PlaySync() ; "
                    f"Add-Type -AssemblyName presentationCore ; "
                    f"$m=New-Object System.Windows.Media.MediaPlayer ; "
                    f"$m.Open([uri]'{tmp_path}') ; "
                    f"$m.Play() ; "
                    f"Start-Sleep -s 5 ; "
                    f"$m.Stop()",
                ],
                timeout=10,
                check=False,
                capture_output=True,
            )
        except Exception:
            pass
        finally:
            import os

            if os.path.exists(tmp_path):
                os.remove(tmp_path)
