from __future__ import annotations

import threading
from unittest.mock import MagicMock

from aura.autonomy.module import AutonomyModule
from aura.cognition.goals import GoalManager as CognitionGoalManager
from aura.cognition.scheduling import (
    ContinuousAutonomyRuntime,
    ControlCommandResult,
    RuntimeControlPlane,
    RuntimeOperationalState,
    ScheduleDispatcher,
    ScheduleStore,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.events import (
    EventBus,
)


def test_01_control_plane_construction():
    """Test 1: Construction of RuntimeControlPlane with dependencies."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    control = RuntimeControlPlane(runtime=runtime, clock=clock)
    assert control.get_status() == RuntimeOperationalState.STOPPED
    assert control.get_audit_history() == []


def test_02_start_command_execution():
    """Test 2: start() command transition from STOPPED to RUNNING."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    event_bus = EventBus()
    events_received: list[str] = []

    event_bus.subscribe(
        "RuntimeControlCommandCompleted", lambda e: events_received.append(e.__event_name__)
    )

    control = RuntimeControlPlane(runtime=runtime, clock=clock, event_bus=event_bus)

    res = control.start()
    try:
        assert res.success
        assert res.command == "START"
        assert res.previous_state == "STOPPED"
        assert res.resulting_state == "RUNNING"
        assert control.get_status() == RuntimeOperationalState.RUNNING
        assert len(events_received) == 1
    finally:
        control.stop()


def test_03_start_idempotency():
    """Test 3: Calling start() on already running runtime is idempotent."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    control = RuntimeControlPlane(runtime=runtime, clock=clock)

    res1 = control.start()
    try:
        assert res1.success
        res2 = control.start()
        assert res2.success
        assert res2.message == "Runtime already running"
        assert len(control.get_audit_history()) == 2
    finally:
        control.stop()


def test_04_stop_command_execution():
    """Test 4: stop() command transition from RUNNING to STOPPED."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    control = RuntimeControlPlane(runtime=runtime, clock=clock)

    control.start()
    res = control.stop()

    assert res.success
    assert res.command == "STOP"
    assert res.previous_state == "RUNNING"
    assert res.resulting_state == "STOPPED"
    assert control.get_status() == RuntimeOperationalState.STOPPED


def test_05_stop_idempotency():
    """Test 5: Calling stop() on already stopped runtime is idempotent."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    control = RuntimeControlPlane(runtime=runtime, clock=clock)

    res = control.stop()

    assert res.success
    assert res.message == "Runtime already stopped"


def test_06_restart_command_execution():
    """Test 6: restart() command executes stop + start cleanly."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    control = RuntimeControlPlane(runtime=runtime, clock=clock)

    control.start()
    try:
        res = control.restart()
        assert res.success
        assert res.command == "RESTART"
        assert control.get_status() == RuntimeOperationalState.RUNNING
    finally:
        control.stop()


def test_07_recover_command_execution():
    """Test 7: recover() on running runtime is idempotent."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    control = RuntimeControlPlane(runtime=runtime, clock=clock)

    control.start()
    try:
        res = control.recover()
        assert res.success
        assert res.message == "Runtime already healthy and running"
    finally:
        control.stop()


def test_08_recover_stopped_runtime_fails():
    """Test 8: recover() on stopped runtime returns success=False."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    control = RuntimeControlPlane(runtime=runtime, clock=clock)

    res = control.recover()

    assert not res.success
    assert "Cannot recover legally stopped runtime" in res.message


def test_09_control_disabled_via_config():
    """Test 9: Commands return success=False when control_enabled is False."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    config = ConfigurationManager()
    config.set("autonomy.control_enabled", False)

    control = RuntimeControlPlane(runtime=runtime, clock=clock, config=config)

    res = control.start()
    assert not res.success
    assert "Control Plane is disabled" in res.message


def test_10_audit_history_bounded():
    """Test 10: Audit history is bounded by control_history_size."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    config = ConfigurationManager()
    config.set("autonomy.control_history_size", 3)

    control = RuntimeControlPlane(runtime=runtime, clock=clock, config=config)

    for _ in range(5):
        control.stop()

    history = control.get_audit_history()
    assert len(history) == 3


def test_11_event_publishing_on_control_commands():
    """Test 11: Events published on command execution."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    event_bus = EventBus()
    issued: list[str] = []
    completed: list[str] = []
    state_changed: list[str] = []

    event_bus.subscribe("RuntimeControlCommandIssued", lambda e: issued.append(e.command))
    event_bus.subscribe("RuntimeControlCommandCompleted", lambda e: completed.append(e.command))
    event_bus.subscribe("RuntimeStateChanged", lambda e: state_changed.append(e.new_state))

    control = RuntimeControlPlane(runtime=runtime, clock=clock, event_bus=event_bus)

    control.start()
    try:
        assert issued == ["START"]
        assert completed == ["START"]
        assert state_changed == ["RUNNING"]
    finally:
        control.stop()


def test_12_autonomy_module_integration():
    """Test 12: AutonomyModule initializes and exposes RuntimeControlPlane."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)

    module = AutonomyModule(clock=clock, runtime=runtime)
    module.on_initialize()

    control = module.get_runtime_control()
    assert control is not None
    assert module.get_runtime_status() == "STOPPED"


def test_13_concurrent_control_commands():
    """Test 13: Multiple concurrent threads calling start, stop, restart, recover."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    control = RuntimeControlPlane(runtime=runtime, clock=clock)

    results: list[ControlCommandResult] = []
    errors: list[Exception] = []

    def worker(cmd: str):
        try:
            if cmd == "start":
                results.append(control.start())
            elif cmd == "stop":
                results.append(control.stop())
            elif cmd == "restart":
                results.append(control.restart())
            elif cmd == "recover":
                results.append(control.recover())
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(cmd,))
        for cmd in ["start", "start", "stop", "restart", "recover"]
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0
    assert len(results) == 5
    control.stop()


def test_14_read_only_queries_have_no_side_effects():
    """Test 14: Read-only queries (get_telemetry, get_diagnostics) do not alter state."""
    clock = TestClock("2026-08-17T10:00:00+00:00")
    store = MagicMock(spec=ScheduleStore)
    goals = MagicMock(spec=CognitionGoalManager)
    dispatcher = ScheduleDispatcher(schedule_store=store, goal_manager=goals)
    runtime = ContinuousAutonomyRuntime(dispatcher=dispatcher, clock=clock)
    control = RuntimeControlPlane(runtime=runtime, clock=clock)

    t1 = control.get_telemetry()
    d1 = control.get_diagnostics()
    h1 = control.get_history()

    assert t1 is not None
    assert d1 is not None
    assert isinstance(h1, list)
    assert control.get_status() == RuntimeOperationalState.STOPPED
    assert len(control.get_audit_history()) == 0
