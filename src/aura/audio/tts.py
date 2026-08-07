from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


@dataclass
class TTSResult:
    audio_bytes: bytes
    text: str
    duration_seconds: float = 1.0


class TTSProvider(ABC):
    """Abstract interface for Text-to-Speech providers (Piper, Coqui, ElevenLabs)."""

    @abstractmethod
    def synthesize(self, text: str, voice: str = "default") -> TTSResult: ...


class MockTTSProvider(TTSProvider):
    """Mock Text-to-Speech provider for testing."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def synthesize(self, text: str, voice: str = "default") -> TTSResult:
        audio_data = text.encode("utf-8")
        result = TTSResult(audio_bytes=audio_data, text=text, duration_seconds=len(text) * 0.05)

        if self.event_bus is not None:
            from ..events import AudioPlaybackFinished, AudioPlaybackStarted, SpeechSynthesized

            self.event_bus.publish(
                SpeechSynthesized(
                    source="MockTTSProvider",
                    text=text,
                    audio_bytes_length=len(audio_data),
                )
            )
            self.event_bus.publish(AudioPlaybackStarted(source="MockTTSProvider", text=text))
            self.event_bus.publish(AudioPlaybackFinished(source="MockTTSProvider", text=text))

        return result
