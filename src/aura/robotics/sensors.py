from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


@dataclass
class SensorData:
    sensor_type: str
    value: float
    unit: str = ""


class SensorManager(ABC):
    """Abstract interface for telemetry and physical sensors (IMU, LiDAR, Battery)."""

    @abstractmethod
    def read_sensor(self, sensor_type: str) -> SensorData: ...

    @abstractmethod
    def read_all_sensors(self) -> list[SensorData]: ...


class MockSensorManager(SensorManager):
    """Mock Sensor Manager for testing."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def read_sensor(self, sensor_type: str) -> SensorData:
        value = 100.0 if sensor_type == "battery" else 0.5
        unit = "%" if sensor_type == "battery" else "m"
        data = SensorData(sensor_type=sensor_type, value=value, unit=unit)

        if self.event_bus is not None:
            from ..events import SensorDataReceived

            self.event_bus.publish(
                SensorDataReceived(
                    source="MockSensorManager",
                    sensor_type=data.sensor_type,
                    value=data.value,
                    unit=data.unit,
                )
            )
        return data

    def read_all_sensors(self) -> list[SensorData]:
        return [
            self.read_sensor("battery"),
            self.read_sensor("distance_front"),
            self.read_sensor("imu_yaw"),
        ]
