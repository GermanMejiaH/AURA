from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


@dataclass
class STTResult:
    text: str
    confidence: float = 1.0
    language: str = "es"


class STTProvider(ABC):
    """Abstract interface for Speech-to-Text providers (Whisper, Vosk, Google STT)."""

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, language: str = "es") -> STTResult:
        ...


class MockSTTProvider(STTProvider):
    """Mock Speech-to-Text provider for testing."""

    def __init__(
        self,
        default_transcript: str = "Hola AURA, ¿cuál es el estado del sistema?",
        event_bus: EventBus | None = None,
    ) -> None:
        self.default_transcript = default_transcript
        self.event_bus = event_bus

    def transcribe(self, audio_bytes: bytes, language: str = "es") -> STTResult:
        if not audio_bytes or audio_bytes in (b"dummy_audio", b"mock"):
            transcript = self.default_transcript
        else:
            try:
                transcript = audio_bytes.decode("utf-8", errors="ignore")
            except Exception:
                transcript = self.default_transcript
        result = STTResult(text=transcript, confidence=0.99, language=language)

        if self.event_bus is not None:
            from ..events import SpeechRecognized

            self.event_bus.publish(
                SpeechRecognized(
                    source="MockSTTProvider",
                    text=result.text,
                    confidence=result.confidence,
                    language=language,
                )
            )
        return result
