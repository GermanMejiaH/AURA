from __future__ import annotations

from aura.core import LifecycleManager, SystemState
from aura.events import EventBus, LifecycleStateChanged


def test_lifecycle_initial_state_is_stopped():
    lc = LifecycleManager()
    assert lc.state == SystemState.STOPPED
    assert lc.is_stopped
    assert not lc.is_running
    assert not lc.is_booting


def test_valid_transition_booting_running_flow():
    lc = LifecycleManager()
    assert lc.boot()
    assert lc.state == SystemState.BOOTING
    assert lc.is_booting

    assert lc.initialize()
    assert lc.state == SystemState.INITIALIZING

    assert lc.start()
    assert lc.state == SystemState.RUNNING
    assert lc.is_running
    assert lc.uptime_seconds >= 0.0


def test_invalid_transition_returns_false():
    lc = LifecycleManager()
    assert not lc.transition_to(SystemState.RUNNING, "invalid-jump")
    assert lc.state == SystemState.STOPPED


def test_transition_publishes_event():
    bus = EventBus()
    lc = LifecycleManager()
    lc.attach_bus(bus)
    lc.boot()

    events = [e for e in bus.history() if isinstance(e, LifecycleStateChanged)]
    assert len(events) == 1
    ev = events[0]
    assert ev.previous_state == SystemState.STOPPED.value
    assert ev.new_state == SystemState.BOOTING.value


def test_callbacks_are_triggered():
    lc = LifecycleManager()
    log: list[tuple[SystemState, SystemState]] = []
    lc.on_transition(lambda p, n: log.append((p, n)))
    lc.boot()
    lc.initialize()
    assert log == [
        (SystemState.STOPPED, SystemState.BOOTING),
        (SystemState.BOOTING, SystemState.INITIALIZING),
    ]


def test_degrade_and_shutdown_flow():
    lc = LifecycleManager()
    lc.boot()
    lc.initialize()
    lc.start()
    assert lc.degrade(reason="some_module_down")
    assert lc.state == SystemState.DEGRADED
    assert lc.is_running

    assert lc.begin_shutdown(reason="manual")
    assert lc.state == SystemState.SHUTTING_DOWN

    assert lc.stop(reason="ended")
    assert lc.state == SystemState.STOPPED
    assert lc.is_stopped


def test_allowed_targets_listed():
    lc = LifecycleManager()
    assert lc.state == SystemState.STOPPED
    targets = lc.allowed_targets()
    assert SystemState.BOOTING in targets
    assert SystemState.RECOVERY in targets


def test_history_is_recorded():
    lc = LifecycleManager()
    lc.boot()
    lc.initialize()
    history = lc.history()
    assert len(history) >= 3
    states = [s for s, _, _ in history]
    assert SystemState.STOPPED in states
    assert SystemState.BOOTING in states
    assert SystemState.INITIALIZING in states
