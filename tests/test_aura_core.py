from __future__ import annotations

import time

from aura import AURA, AURABootOptions, BaseModule, ModuleStatus, SystemState


class CounterModule(BaseModule):
    name = "counter"
    description = "Module that counts starts"
    starts = 0

    def on_initialize(self) -> None:
        self.count = 0

    def on_start(self) -> None:
        CounterModule.starts += 1
        self.count = CounterModule.starts


def test_aura_boot_and_shutdown_cycle():
    opts = AURABootOptions(
        log_level="WARNING",
        enable_scheduler=False,
        enable_health_monitor=False,
        auto_discover_modules=False,
        module_classes=[CounterModule],
    )
    aura = AURA(options=opts)
    try:
        aura.boot()
        assert aura.lifecycle.is_running
        assert aura.state in {SystemState.RUNNING, SystemState.DEGRADED}
        mod = aura.module_manager.get("counter")
        assert mod is not None
        assert mod.health.status == ModuleStatus.RUNNING
        assert CounterModule.starts == 1
        events_by_name = [e.event_name() for e in aura.event_bus.history()]
        assert "SystemBooting" in events_by_name
        assert "SystemReady" in events_by_name
    finally:
        aura.shutdown(wait=True)
        assert aura.lifecycle.is_stopped
        history = [s for s, _, _ in aura.lifecycle.history()]
        assert SystemState.SHUTTING_DOWN in history
        assert SystemState.STOPPED in history
        shutdown_events = [e for e in aura.event_bus.history() if e.event_name() == "SystemStopped"]
        assert len(shutdown_events) == 1


def test_aura_health_report_and_diagnostics_report():
    aura = AURA(
        options=AURABootOptions(
            log_level="CRITICAL",
            enable_scheduler=False,
            enable_health_monitor=True,
            auto_discover_modules=False,
            module_classes=[CounterModule],
        )
    )
    try:
        aura.boot()
        report = aura.health_report()
        assert "overall" in report
        assert report["modules_total"] >= 1
        text = aura.diagnostics_report()
        assert "AURA Diagnostics Report" in text
        assert "counter" in text
    finally:
        aura.shutdown(wait=True)


def test_aura_request_shutdown_sets_event():
    aura = AURA(
        options=AURABootOptions(
            log_level="CRITICAL",
            enable_scheduler=False,
            enable_health_monitor=False,
        )
    )
    aura.boot()
    assert not aura._shutdown_event.is_set()
    aura.request_shutdown(reason="test")
    assert aura._shutdown_event.is_set()
    aura.shutdown(wait=True)
