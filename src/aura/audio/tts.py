from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class TTSResult:
    audio_bytes: bytes
    text: str
    duration_seconds: float = 1.0
    load_model_ms: float = 0.0
    synthesize_ms: float = 0.0
    save_audio_ms: float = 0.0
    playback_ms: float = 0.0


class TTSProvider(ABC):
    """Abstract interface for Text-to-Speech providers (Piper, Coqui, ElevenLabs)."""

    @abstractmethod
    def synthesize(self, text: str, voice: str = "default") -> TTSResult: ...

    def stop(self) -> None:
        """Interrupts and stops ongoing speech playback."""
        pass


class MockTTSProvider(TTSProvider):
    """Mock Text-to-Speech provider for testing."""

    def synthesize(self, text: str, voice: str = "default") -> TTSResult:
        audio_data = text.encode("utf-8")
        return TTSResult(
            audio_bytes=audio_data,
            text=text,
            duration_seconds=max(0.1, len(text) * 0.05),
        )
