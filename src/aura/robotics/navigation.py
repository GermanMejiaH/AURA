from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


@dataclass
class Waypoint:
    x: float
    y: float
    z: float = 0.0
    orientation: float = 0.0


class NavigationSystem(ABC):
    """Abstract interface for robotic trajectory planning and navigation."""

    @abstractmethod
    def navigate_to(self, waypoint: Waypoint) -> bool:
        ...

    @abstractmethod
    def cancel_navigation(self) -> None:
        ...


class MockNavigationSystem(NavigationSystem):
    """Mock Navigation System for testing."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self.current_position = Waypoint(x=0.0, y=0.0, z=0.0)

    def navigate_to(self, waypoint: Waypoint) -> bool:
        self.current_position = waypoint

        if self.event_bus is not None:
            from ..events import NavigationTargetReached

            self.event_bus.publish(
                NavigationTargetReached(
                    source="MockNavigationSystem",
                    waypoint_x=waypoint.x,
                    waypoint_y=waypoint.y,
                )
            )
        return True

    def cancel_navigation(self) -> None:
        pass
