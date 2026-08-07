from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


@dataclass
class MotorCommand:
    joint_id: str
    target_position: float
    speed: float = 1.0
    torque: float = 1.0


class MotorController(ABC):
    """Abstract interface for motor controllers and physical actuators (ROS2, CAN, Serial)."""

    @abstractmethod
    def move_joint(self, command: MotorCommand) -> bool:
        ...

    @abstractmethod
    def set_wheel_velocity(self, linear_v: float, angular_v: float) -> bool:
        ...

    @abstractmethod
    def stop_all(self) -> None:
        ...


class MockMotorController(MotorController):
    """Mock Motor Controller for testing and simulation environments."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self.joint_positions: dict[str, float] = {}

    def move_joint(self, command: MotorCommand) -> bool:
        self.joint_positions[command.joint_id] = command.target_position

        if self.event_bus is not None:
            from ..events import MotorMoved

            self.event_bus.publish(
                MotorMoved(
                    source="MockMotorController",
                    joint_id=command.joint_id,
                    position=command.target_position,
                )
            )
        return True

    def set_wheel_velocity(self, linear_v: float, angular_v: float) -> bool:
        return True

    def stop_all(self) -> None:
        pass
