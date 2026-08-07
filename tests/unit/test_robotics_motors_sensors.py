from __future__ import annotations

from aura.events import EventBus, MotorMoved, SensorDataReceived
from aura.robotics import MockMotorController, MockSensorManager, MotorCommand


def test_motor_controller_and_events():
    bus = EventBus()
    motors = MockMotorController(event_bus=bus)

    moved_events: list[MotorMoved] = []
    bus.subscribe("MotorMoved", lambda e: moved_events.append(e))

    cmd = MotorCommand(joint_id="arm_joint_1", target_position=1.57)
    res = motors.move_joint(cmd)

    assert res is True
    assert motors.joint_positions["arm_joint_1"] == 1.57
    assert len(moved_events) == 1
    assert moved_events[0].joint_id == "arm_joint_1"
    assert moved_events[0].position == 1.57


def test_sensor_manager_and_events():
    bus = EventBus()
    sensors = MockSensorManager(event_bus=bus)

    sensor_events: list[SensorDataReceived] = []
    bus.subscribe("SensorDataReceived", lambda e: sensor_events.append(e))

    bat_data = sensors.read_sensor("battery")
    assert bat_data.sensor_type == "battery"
    assert bat_data.value == 100.0

    all_data = sensors.read_all_sensors()
    assert len(all_data) == 3
    assert len(sensor_events) == 4  # 1 from read_sensor + 3 from read_all_sensors
