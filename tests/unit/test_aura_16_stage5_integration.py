from __future__ import annotations

from unittest.mock import MagicMock

from aura.autonomy.agent_models import AgentGoal, AgentPlan, AgentTask, TaskStatus
from aura.autonomy.executor import AgentExecutionResult, AgentExecutor
from aura.autonomy.module import AutonomyModule
from aura.autonomy.planner import AgentPlanner
from aura.cognition.goals import GoalManager, GoalStatus, GoalStore
from aura.cognition.scheduling import (
    Clock,
    ContinuousAutonomyRuntime,
    ScheduleDispatcher,
    ScheduleStatus,
    ScheduleStore,
    ScheduleType,
    TemporalSchedule,
    TestClock,
)
from aura.config import ConfigurationManager
from aura.core.aura import AURA, AURABootOptions
from aura.memory.store import SQLiteMemoryStore


def test_01_boot_initializes_and_starts_runtime():
    """Test 01: AURA.boot() initializes AutonomyModule and starts ContinuousAutonomyRuntime."""
    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts)
    aura.boot()

    assert aura.is_booted
    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    assert mod.runtime is not None
    assert mod.runtime.is_running

    aura.shutdown(wait=True)
    assert not mod.runtime.is_running


def test_02_boot_does_not_create_duplicate_runtimes():
    """Test 02: Repeated calls to AURA.boot() do not create duplicate runtimes."""
    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts)
    aura.boot()
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    runtime = mod.runtime
    assert runtime is not None
    assert runtime.is_running

    aura.shutdown(wait=True)
    assert not runtime.is_running


def test_03_shutdown_stops_runtime_cleanly():
    """Test 03: AURA.shutdown() cleanly stops ContinuousAutonomyRuntime without orphan threads."""
    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts)
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    assert mod.runtime is not None
    assert mod.runtime.is_running

    runtime_thread = mod.runtime._thread
    assert runtime_thread is not None
    assert runtime_thread.is_alive()

    aura.shutdown(wait=True)

    assert not mod.runtime.is_running
    assert not runtime_thread.is_alive()


def test_04_shutdown_repeated_is_safe_and_idempotent():
    """Test 04: Multiple calls to AURA.shutdown() are safe and idempotent."""
    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts)
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)

    aura.shutdown(wait=True)
    assert not mod.runtime.is_running

    # Second shutdown is a no-op
    res = aura.shutdown(wait=True)
    assert res is True
    assert not mod.runtime.is_running


def test_05_boot_rollback_stops_runtime():
    """Test 05: Failure during boot triggers _rollback_boot() and stops runtime cleanly."""
    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts)

    # Mock step 8 to raise exception
    aura._step8_become_ready = MagicMock(side_effect=RuntimeError("Step 8 simulated failure"))

    try:
        aura.boot()
    except RuntimeError:
        pass

    assert not aura.is_booted
    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    if mod and mod.runtime:
        assert not mod.runtime.is_running


def test_06_configured_tick_interval_loaded():
    """Test 06: Custom tick_interval_seconds from ConfigurationManager is applied to runtime."""
    cfg = ConfigurationManager()
    cfg.load_from_dict({"autonomy.tick_interval_seconds": 0.25})

    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts, config=cfg)
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    assert mod.runtime is not None
    assert mod.runtime.tick_interval_seconds == 0.25

    aura.shutdown(wait=True)


def test_07_ioc_container_resolves_scheduling_components():
    """Test 07: DependencyContainer resolves ScheduleStore, ScheduleDispatcher, Clock, Runtime."""
    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts)
    aura.boot()

    container = aura.container
    assert container.has(ScheduleStore)
    assert container.has(ScheduleDispatcher)
    assert container.has(Clock)
    assert container.has(ContinuousAutonomyRuntime)

    aura.shutdown(wait=True)


def test_08_runtime_disabled_in_config_does_not_start():
    """Test 08: Setting autonomy.runtime_enabled=False keeps ContinuousAutonomyRuntime stopped."""
    cfg = ConfigurationManager()
    cfg.load_from_dict({"autonomy.runtime_enabled": False})

    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts, config=cfg)
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    assert mod.runtime is not None
    assert not mod.runtime.is_running

    aura.shutdown(wait=True)


def test_09_test_clock_injection_in_autonomy_module():
    """Test 09: TestClock injected into AutonomyModule operates deterministically."""
    clock = TestClock("2026-08-16T12:00:00+00:00")
    autonomy_mod = AutonomyModule(clock=clock)

    opts = AURABootOptions(
        enable_scheduler=False,
        enable_health_monitor=False,
        module_classes=[AutonomyModule],
    )
    aura = AURA(options=opts)
    aura.container.register(AutonomyModule, instance=autonomy_mod)
    aura.boot()

    assert autonomy_mod.clock is clock
    assert autonomy_mod.runtime is not None
    assert autonomy_mod.runtime.clock is clock

    aura.shutdown(wait=True)


def test_10_e2e_schedule_execution_through_boot(tmp_path):
    """Test 10: E2E Integration: Schedule created prior to boot is processed during runtime tick."""
    db_file = str(tmp_path / "stage5_e2e.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    goal_mgr = GoalManager(store=GoalStore(store=sql_store))
    sched_store = ScheduleStore(store=sql_store)

    planner = MagicMock(spec=AgentPlanner)
    executor = MagicMock(spec=AgentExecutor)
    mock_plan = AgentPlan(
        goal=AgentGoal(description="E2E Boot Schedule Goal"),
        tasks=[AgentTask(description="Task 1", status=TaskStatus.SUCCESS)],
    )
    planner.deliberate_and_plan.return_value = (MagicMock(), mock_plan)
    executor.execute_plan.return_value = AgentExecutionResult(
        plan_id=mock_plan.plan_id, completed=True
    )

    clock = TestClock("2026-08-16T10:00:00+00:00")
    dispatcher = ScheduleDispatcher(
        schedule_store=sched_store,
        goal_manager=goal_mgr,
        planner=planner,
        executor=executor,
    )
    autonomy_mod = AutonomyModule(
        goal_manager=goal_mgr,
        schedule_store=sched_store,
        schedule_dispatcher=dispatcher,
        clock=clock,
    )

    goal = goal_mgr.create_goal("E2E Boot Schedule Goal")
    past = "2026-08-16T09:55:00+00:00"
    sched = TemporalSchedule(
        goal_id=goal.goal_id,
        schedule_type=ScheduleType.ONE_SHOT,
        next_run_at=past,
    )
    sched_store.save_schedule(sched)

    opts = AURABootOptions(
        enable_scheduler=False,
        enable_health_monitor=False,
        module_classes=[AutonomyModule],
    )
    aura = AURA(options=opts)
    aura.container.register(AutonomyModule, instance=autonomy_mod)
    aura.boot()

    assert autonomy_mod.runtime is not None
    results = autonomy_mod.runtime.tick()

    assert len(results) == 1
    assert results[0].dispatched is True

    updated_goal = goal_mgr.get_goal(goal.goal_id)
    assert updated_goal is not None
    assert updated_goal.status == GoalStatus.COMPLETED

    retrieved_sched = sched_store.get_schedule(sched.schedule_id)
    assert retrieved_sched is not None
    assert retrieved_sched.status == ScheduleStatus.COMPLETED

    aura.shutdown(wait=True)


def test_11_autonomy_disabled_with_runtime_enabled_does_not_start():
    """Test 11: autonomy.enabled=False prevents runtime start even if runtime_enabled=True."""
    cfg = ConfigurationManager()
    cfg.load_from_dict(
        {
            "autonomy.enabled": False,
            "autonomy.runtime_enabled": True,
        }
    )

    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts, config=cfg)
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    assert mod.runtime is not None
    assert not mod.runtime.is_running

    aura.shutdown(wait=True)


def test_12_tick_interval_positive_preserved():
    """Test 12: Positive tick_interval_seconds (> 0) preserves configured value."""
    cfg = ConfigurationManager()
    cfg.load_from_dict({"autonomy.tick_interval_seconds": 2.5})

    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts, config=cfg)
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    assert mod.runtime is not None
    assert mod.runtime.tick_interval_seconds == 2.5

    aura.shutdown(wait=True)


def test_13_tick_interval_zero_clamped_to_minimum():
    """Test 13: tick_interval_seconds == 0 is clamped to minimum safe value (0.05)."""
    cfg = ConfigurationManager()
    cfg.load_from_dict({"autonomy.tick_interval_seconds": 0.0})

    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts, config=cfg)
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    assert mod.runtime is not None
    assert mod.runtime.tick_interval_seconds == 0.05

    aura.shutdown(wait=True)


def test_14_tick_interval_negative_clamped_to_minimum():
    """Test 14: Negative tick_interval_seconds (< 0) is clamped to minimum safe value (0.05)."""
    cfg = ConfigurationManager()
    cfg.load_from_dict({"autonomy.tick_interval_seconds": -10.0})

    opts = AURABootOptions(enable_scheduler=False, enable_health_monitor=False)
    aura = AURA(options=opts, config=cfg)
    aura.boot()

    mod = aura.module_manager.get("autonomy") if aura.module_manager else None
    assert isinstance(mod, AutonomyModule)
    assert mod.runtime is not None
    assert mod.runtime.tick_interval_seconds == 0.05

    aura.shutdown(wait=True)
