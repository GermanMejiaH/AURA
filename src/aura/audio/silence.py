from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


class SilenceDetector:
    """Voice Activity & Silence Detector for managing conversational turns."""

    def __init__(
        self,
        silence_threshold_seconds: float = 1.5,
        event_bus: EventBus | None = None,
    ) -> None:
        self.silence_threshold = silence_threshold_seconds
        self.event_bus = event_bus
        self._lock = threading.RLock()

    def process_silence_duration(self, duration_seconds: float) -> bool:
        with self._lock:
            if duration_seconds >= self.silence_threshold:
                if self.event_bus is not None:
                    from ..events import SilenceDetected

                    self.event_bus.publish(
                        SilenceDetected(
                            source="SilenceDetector",
                            duration_seconds=duration_seconds,
                        )
                    )
                return True
            return False
