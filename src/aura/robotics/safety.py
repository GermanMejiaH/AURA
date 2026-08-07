from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


class SafetySystem:
    """Robotic Safety Interlock System (E-Stop, collision prevention, boundaries)."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self.is_emergency_stopped: bool = False

    def trigger_emergency_stop(self, reason: str = "user_e_stop") -> None:
        self.is_emergency_stopped = True

        if self.event_bus is not None:
            from ..events import EmergencyStopTriggered

            self.event_bus.publish(
                EmergencyStopTriggered(source="SafetySystem", reason=reason)
            )

    def reset_emergency_stop(self) -> None:
        self.is_emergency_stopped = False

    def report_hazard(self, message: str, level: str = "WARNING") -> None:
        if self.event_bus is not None:
            from ..events import SafetyAlert

            self.event_bus.publish(
                SafetyAlert(source="SafetySystem", level=level, message=message)
            )
