from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


@dataclass
class GraspCommand:
    target_object_id: str
    grasp_force: float = 1.0


class Manipulator(ABC):
    """Abstract interface for robotic end-effectors, grippers and manipulators."""

    @abstractmethod
    def grasp_object(self, command: GraspCommand) -> bool: ...

    @abstractmethod
    def release_object(self, target_object_id: str) -> bool: ...


class MockManipulator(Manipulator):
    """Mock Manipulator for testing."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self.grasped_objects: set[str] = set()

    def grasp_object(self, command: GraspCommand) -> bool:
        self.grasped_objects.add(command.target_object_id)

        if self.event_bus is not None:
            from ..events import ObjectManipulated

            self.event_bus.publish(
                ObjectManipulated(
                    source="MockManipulator",
                    object_id=command.target_object_id,
                    action="grasp",
                    success=True,
                )
            )
        return True

    def release_object(self, target_object_id: str) -> bool:
        self.grasped_objects.discard(target_object_id)

        if self.event_bus is not None:
            from ..events import ObjectManipulated

            self.event_bus.publish(
                ObjectManipulated(
                    source="MockManipulator",
                    object_id=target_object_id,
                    action="release",
                    success=True,
                )
            )
        return True
