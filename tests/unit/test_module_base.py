from __future__ import annotations

import pytest

from aura.modules.base import BaseModule, ModuleStatus


class DummySuccessModule(BaseModule):
    name = "dummy-success"

    def on_initialize(self) -> None:
        pass


class DummyFailingStartModule(BaseModule):
    name = "failing-start"

    def on_initialize(self) -> None:
        pass

    def on_start(self) -> None:
        raise RuntimeError("Start failed intentionally")


class DummyFailingInitModule(BaseModule):
    name = "failing-init"

    def on_initialize(self) -> None:
        raise ValueError("Init failed intentionally")


class DummyFailingPauseModule(BaseModule):
    name = "failing-pause"

    def on_initialize(self) -> None:
        pass

    def on_pause(self) -> None:
        raise RuntimeError("Pause failed")


class DummyFailingResumeModule(BaseModule):
    name = "failing-resume"

    def on_initialize(self) -> None:
        pass

    def on_resume(self) -> None:
        raise RuntimeError("Resume failed")


def test_base_module_successful_lifecycle():
    mod = DummySuccessModule()
    assert mod.health.status == ModuleStatus.UNLOADED

    mod.load()
    assert mod.health.status == ModuleStatus.LOADED

    mod.initialize()
    assert mod.health.status == ModuleStatus.READY
    assert mod.is_initialized is True

    mod.start()
    assert mod.health.status == ModuleStatus.RUNNING

    mod.pause()
    assert mod.health.status == ModuleStatus.PAUSED

    mod.resume()
    assert mod.health.status == ModuleStatus.RUNNING

    mod.stop()
    assert mod.health.status == ModuleStatus.STOPPED

    mod.shutdown()


def test_base_module_failing_initialize_sets_error():
    mod = DummyFailingInitModule()
    with pytest.raises(ValueError, match="Init failed intentionally"):
        mod.initialize()

    assert mod.health.status == ModuleStatus.ERROR
    assert "Init failed intentionally" in str(mod.health.last_error)
    assert mod.is_initialized is False


def test_base_module_failing_start_sets_error():
    mod = DummyFailingStartModule()
    mod.initialize()
    assert mod.health.status == ModuleStatus.READY

    with pytest.raises(RuntimeError, match="Start failed intentionally"):
        mod.start()

    assert mod.health.status == ModuleStatus.ERROR
    assert "Start failed intentionally" in str(mod.health.last_error)


def test_base_module_failing_pause_resume():
    mod = DummyFailingPauseModule()
    mod.initialize()
    mod.start()

    with pytest.raises(RuntimeError, match="Pause failed"):
        mod.pause()
    assert mod.health.status == ModuleStatus.ERROR

    mod2 = DummyFailingResumeModule()
    mod2.initialize()
    mod2.start()
    mod2.pause()
    with pytest.raises(RuntimeError, match="Resume failed"):
        mod2.resume()
    assert mod2.health.status == ModuleStatus.ERROR


def test_base_module_shutdown_idempotency():
    mod = DummySuccessModule()
    mod.shutdown()
    mod.shutdown()
    assert mod.health.status == ModuleStatus.UNLOADED
