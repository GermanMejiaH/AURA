from __future__ import annotations

from typing import ClassVar

from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.core.lifecycle import LifecycleManager
from aura.core.module_manager import ModuleManager
from aura.events import EventBus
from aura.modules.base import BaseModule, ModuleStatus


class ModA(BaseModule):
    name = "mod-a"
    stop_order: ClassVar[list[str]] = []

    def on_initialize(self) -> None:
        pass

    def on_stop(self) -> None:
        ModA.stop_order.append(self.name)


class ModB(BaseModule):
    name = "mod-b"

    def on_initialize(self) -> None:
        pass

    def on_stop(self) -> None:
        ModA.stop_order.append(self.name)
        raise RuntimeError("ModB stop failed")


class ModC(BaseModule):
    name = "mod-c"

    def on_initialize(self) -> None:
        pass

    def on_stop(self) -> None:
        ModA.stop_order.append(self.name)


def test_module_manager_reverse_stop_order_and_error_handling():
    ModA.stop_order.clear()
    config = ConfigurationManager()
    container = DependencyContainer()
    event_bus = EventBus()
    lifecycle = LifecycleManager()

    mm = ModuleManager(
        config=config,
        container=container,
        event_bus=event_bus,
        lifecycle=lifecycle,
    )

    mod_a = mm.register(ModA)
    mod_b = mm.register(ModB)
    mod_c = mm.register(ModC)

    mm.initialize_all()
    mm.start_all()

    assert mod_a.health.status == ModuleStatus.RUNNING
    assert mod_b.health.status == ModuleStatus.RUNNING
    assert mod_c.health.status == ModuleStatus.RUNNING

    stop_results = mm.stop_all()

    # Modules should stop in reverse order: ModC -> ModB -> ModA
    assert ModA.stop_order == ["mod-c", "mod-b", "mod-a"]

    assert stop_results["mod-c"] is True
    assert stop_results["mod-b"] is False
    assert stop_results["mod-a"] is True

    # ModB should preserve ERROR status
    assert mod_b.health.status == ModuleStatus.ERROR
    assert mod_a.health.status == ModuleStatus.STOPPED
    assert mod_c.health.status == ModuleStatus.STOPPED
