from __future__ import annotations

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import Event, EventBus
from ..logging import get_logger
from ..modules.base import BaseModule
from .manipulation import GraspCommand, Manipulator, MockManipulator
from .motors import MockMotorController, MotorCommand, MotorController
from .navigation import MockNavigationSystem, NavigationSystem, Waypoint
from .safety import SafetySystem
from .sensors import MockSensorManager, SensorManager


class RoboticsModule(BaseModule):
    """Core module managing physical body interactions & safety."""

    name = "robotics"
    description = "Robotics System - Actuators, Telemetry, Navigation, Manipulation & E-Stop Safety"
    priority = 55

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        container: DependencyContainer | None = None,
        event_bus: EventBus | None = None,
        motor_controller: MotorController | None = None,
        sensor_manager: SensorManager | None = None,
        navigation_system: NavigationSystem | None = None,
        manipulator: Manipulator | None = None,
        safety_system: SafetySystem | None = None,
    ) -> None:
        super().__init__(config, container, event_bus)
        self.motors = motor_controller or MockMotorController(event_bus=event_bus)
        self.sensors = sensor_manager or MockSensorManager(event_bus=event_bus)
        self.navigation = navigation_system or MockNavigationSystem(event_bus=event_bus)
        self.manipulator = manipulator or MockManipulator(event_bus=event_bus)
        self.safety = safety_system or SafetySystem(event_bus=event_bus)

    def on_initialize(self) -> None:
        logger = get_logger("RoboticsModule")

        # Register IoC instances
        if self._container is not None:
            self._container.register(MotorController, instance=self.motors)
            self._container.register(SensorManager, instance=self.sensors)
            self._container.register(NavigationSystem, instance=self.navigation)
            self._container.register(Manipulator, instance=self.manipulator)
            self._container.register(SafetySystem, instance=self.safety)

        # Event Subscriptions
        self.subscribe("ActionDispatched", self._on_action_dispatched)

        logger.info("RoboticsModule initialized")

    def _on_action_dispatched(self, event: Event) -> None:
        if self.safety.is_emergency_stopped:
            return

        action_type = getattr(event, "action_type", "") or event.payload.get("action_type", "")

        if action_type == "move_joint":
            joint_id = event.payload.get("joint_id", "joint_1")
            pos = float(event.payload.get("position", 0.0))
            self.motors.move_joint(MotorCommand(joint_id=joint_id, target_position=pos))
        elif action_type == "navigate":
            x = float(event.payload.get("x", 0.0))
            y = float(event.payload.get("y", 0.0))
            self.navigation.navigate_to(Waypoint(x=x, y=y))
        elif action_type == "grasp":
            obj_id = event.payload.get("target_object_id", "object_1")
            self.manipulator.grasp_object(GraspCommand(target_object_id=obj_id))
        elif action_type == "release":
            obj_id = event.payload.get("target_object_id", "object_1")
            self.manipulator.release_object(obj_id)
        elif action_type == "e_stop":
            self.safety.trigger_emergency_stop(reason="ActionDispatched")
