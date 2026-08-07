from __future__ import annotations

from dataclasses import dataclass

from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.core import AURA, AURABootOptions, SystemState
from aura.diagnostics import Diagnostics
from aura.events import Event, EventBus
from aura.health import HealthMonitor
from aura.logging import AuraLogger
from aura.modules.base import BaseModule, ModuleStatus


class DummySensorModule(BaseModule):
    name = "dummy_sensor"
    description = "Mock sensor module for integration testing"

    def __init__(
        self,
        config: ConfigurationManager,
        container: DependencyContainer,
        event_bus: EventBus,
    ) -> None:
        super().__init__(config, container, event_bus)
        self.events_received: list[Event] = []

    def on_initialize(self) -> None:
        self.subscribe("PingEvent", self._on_ping)

    def _on_ping(self, event: Event) -> None:
        self.events_received.append(event)


class FailingModule(BaseModule):
    name = "failing_module"
    description = "Module designed to fail startup"

    def on_initialize(self) -> None:
        pass

    def on_start(self) -> None:
        raise RuntimeError("Simulated startup failure")


@dataclass(frozen=True)
class PingEvent(Event):
    msg: str = "ping"


def test_full_foundation_integration_boot_and_shutdown():
    options = AURABootOptions(
        enable_scheduler=True,
        enable_health_monitor=True,
        module_classes=[DummySensorModule],
        log_level="DEBUG",
    )
    aura = AURA(options=options)
    aura.boot()

    assert aura.state == SystemState.RUNNING
    assert aura.is_running is True

    # IoC container assertions
    assert aura.container.has(ConfigurationManager)
    assert aura.container.has(DependencyContainer)
    assert aura.container.has(EventBus)
    assert aura.container.has(AuraLogger)
    assert aura.container.has(Diagnostics)
    assert aura.container.has(HealthMonitor)

    # Event publishing & subscription test
    ping = PingEvent(source="test", msg="hello_aura")
    aura.publish(ping)

    sensor = aura.module_manager.get("dummy_sensor")
    assert sensor is not None
    assert isinstance(sensor, DummySensorModule)
    assert len(sensor.events_received) == 1
    assert sensor.events_received[0].msg == "hello_aura"

    # Diagnostics report test
    report = aura.diagnostics_report()
    assert "AURA Diagnostics Report" in report
    assert "dummy_sensor" in report

    # Health check test
    health = aura.health_report()
    assert health["overall"] == "healthy"
    assert health["modules_total"] >= 1

    # Graceful shutdown test
    aura.shutdown(wait=True)
    assert aura.state == SystemState.STOPPED


def test_foundation_degraded_mode_on_module_failure():
    options = AURABootOptions(
        module_classes=[DummySensorModule, FailingModule],
    )
    aura = AURA(options=options)
    aura.boot()

    assert aura.state == SystemState.DEGRADED
    failing_mod = aura.module_manager.get("failing_module")
    assert failing_mod is not None
    assert failing_mod.health.status == ModuleStatus.ERROR

    aura.shutdown(wait=True)
    assert aura.state == SystemState.STOPPED
