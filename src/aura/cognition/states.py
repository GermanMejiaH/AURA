from __future__ import annotations

import threading
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


class CognitiveState(str, Enum):
    BOOTING = "Booting"
    IDLE = "Idle"
    LISTENING = "Listening"
    THINKING = "Thinking"
    SPEAKING = "Speaking"
    EXECUTING = "Executing"
    OBSERVING = "Observing"
    LEARNING = "Learning"
    SLEEPING = "Sleeping"
    ERROR = "Error"


class CognitiveStateMachine:
    """Manages the current cognitive state of AURA (ADR-002)."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._state: CognitiveState = CognitiveState.BOOTING
        self._lock = threading.RLock()
        self._event_bus = event_bus
        self._history: list[tuple[CognitiveState, CognitiveState, str]] = []

    @property
    def state(self) -> CognitiveState:
        with self._lock:
            return self._state

    def transition_to(self, new_state: CognitiveState, reason: str = "") -> bool:
        with self._lock:
            if self._state == new_state:
                return True

            prev = self._state
            self._state = new_state
            self._history.append((prev, new_state, reason))

            if self._event_bus is not None:
                from ..events import CognitiveStateChanged

                self._event_bus.publish(
                    CognitiveStateChanged(
                        source="CognitiveStateMachine",
                        previous_state=prev.value,
                        new_state=new_state.value,
                        reason=reason,
                    )
                )
            return True

    def history(self) -> list[tuple[CognitiveState, CognitiveState, str]]:
        with self._lock:
            return list(self._history)
