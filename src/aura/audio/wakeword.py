from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


@dataclass
class WakeWordResult:
    detected: bool
    keyword: str = "aura"
    confidence: float = 1.0


class WakeWordDetector(ABC):
    """Abstract interface for Wake Word Detection (e.g. Porcupine, PocketSpinning, Vosk)."""

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @abstractmethod
    def is_active(self) -> bool:
        ...


class MockWakeWordDetector(WakeWordDetector):
    """Mock Wake Word Detector for development and testing."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def is_active(self) -> bool:
        return self._running

    def trigger(self, keyword: str = "aura", confidence: float = 0.98) -> WakeWordResult:
        if self.event_bus is not None:
            from ..events import WakeWordDetected

            self.event_bus.publish(
                WakeWordDetected(
                    source="MockWakeWordDetector",
                    keyword=keyword,
                    confidence=confidence,
                )
            )
        return WakeWordResult(detected=True, keyword=keyword, confidence=confidence)
