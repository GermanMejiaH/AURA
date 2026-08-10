from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


from .types import AudioData


@dataclass
class STTResult:
    text: str
    confidence: float = 1.0
    language: str = "es"


class STTProvider(ABC):
    """Abstract interface for Speech-to-Text providers (Whisper, Vosk, Google STT)."""

    @abstractmethod
    def transcribe(
        self,
        audio: AudioData | bytes,
        language: str = "es",
    ) -> STTResult:
        """Transcribe AudioData or raw audio bytes into text."""
        ...


class MockSTTProvider(STTProvider):
    """Mock Speech-to-Text provider used for testing."""

    def __init__(
        self,
        default_transcript: str = "Hola AURA, ¿cuál es el estado del sistema?",
    ) -> None:
        self.default_transcript = default_transcript

    def transcribe(
        self,
        audio: AudioData | bytes,
        language: str = "es",
    ) -> STTResult:
        if isinstance(audio, AudioData):
            transcript = audio.text_hint if audio.text_hint else self.default_transcript
        elif not audio or audio in (b"dummy_audio", b"mock"):
            transcript = self.default_transcript
        else:
            try:
                decoded = audio.decode("utf-8", errors="ignore").strip()
                transcript = decoded if decoded else self.default_transcript
            except Exception:
                transcript = self.default_transcript

        return STTResult(
            text=transcript,
            confidence=0.99,
            language=language,
        )
