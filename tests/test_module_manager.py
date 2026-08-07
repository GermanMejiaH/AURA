from __future__ import annotations

from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.core import LifecycleManager
from aura.core.module_manager import ModuleManager
from aura.events import EventBus, ModuleLoaded, ModuleStarted
from aura.modules import BaseModule, ModuleStatus


class GoodModule(BaseModule):
    name = "good-mod"
    priority = 10
    version = "0.1.0"
    description = "A module that works fine"

    def on_initialize(self) -> None:
        self.value = 42


class FailingInitModule(BaseModule):
    name = "fail-init"

    def on_initialize(self) -> None:
        raise RuntimeError("boom")


class BrokenStartModule(BaseModule):
    name = "broken-start"

    def on_initialize(self) -> None:
        return None

    def on_start(self) -> None:
        raise RuntimeError("start failed")


def _build_manager() -> ModuleManager:
    cfg = ConfigurationManager()
    container = DependencyContainer()
    bus = EventBus()
    lc = LifecycleManager()
    return ModuleManager(config=cfg, container=container, event_bus=bus, lifecycle=lc)


def test_register_module_loads_and_emits_event():
    mgr = _build_manager()
    mod = mgr.register(GoodModule)
    assert mod.name == "good-mod"
    assert mgr.count() == 1
    assert mgr.get("good-mod") is mod
    load_events = [e for e in mgr.event_bus.history() if isinstance(e, ModuleLoaded)]
    assert len(load_events) == 1
    assert load_events[0].module_name == "good-mod"


def test_initialize_all_marks_ready():
    mgr = _build_manager()
    mgr.register(GoodModule)
    results = mgr.initialize_all()
    assert results["good-mod"] is True
    mod = mgr.get("good-mod")
    assert mod is not None
    assert mod.health.status == ModuleStatus.READY
    assert mod.is_initialized
    assert getattr(mod, "value", None) == 42


def test_start_all_starts_modules():
    mgr = _build_manager()
    mgr.register(GoodModule)
    mgr.initialize_all()
    mgr.start_all()
    started_events = [e for e in mgr.event_bus.history() if isinstance(e, ModuleStarted)]
    assert len(started_events) == 1
    mod = mgr.get("good-mod")
    assert mod is not None
    assert mod.health.status == ModuleStatus.RUNNING


def test_failing_init_does_not_crash_manager():
    mgr = _build_manager()
    mgr.register(GoodModule)
    mgr.register(FailingInitModule)
    results = mgr.initialize_all()
    assert results["good-mod"] is True
    assert results["fail-init"] is False
    fail = mgr.get("fail-init")
    assert fail is not None
    assert fail.health.status == ModuleStatus.ERROR
    assert fail.health.last_error is not None


def test_stop_all_reverses_order():
    mgr = _build_manager()
    order: list[str] = []

    class ModA(BaseModule):
        name = "a"

        def on_initialize(self) -> None:
            return None

        def on_stop(self) -> None:
            order.append(self.name)

    class ModB(BaseModule):
        name = "b"

        def on_initialize(self) -> None:
            return None

        def on_stop(self) -> None:
            order.append(self.name)

    mgr.register(ModA)
    mgr.register(ModB)
    mgr.initialize_all()
    mgr.start_all()
    mgr.stop_all()
    assert order == ["b", "a"]


def test_pause_and_resume():
    mgr = _build_manager()
    mgr.register(GoodModule)
    mgr.initialize_all()
    mgr.start_all()
    mgr.pause_all()
    mod = mgr.get("good-mod")
    assert mod.health.status == ModuleStatus.PAUSED
    mgr.resume_all()
    assert mod.health.status == ModuleStatus.RUNNING


def test_list_returns_ordered():
    mgr = _build_manager()
    mgr.register(GoodModule)
    items = mgr.list_modules()
    assert len(items) == 1
    assert items[0][0] == "good-mod"
