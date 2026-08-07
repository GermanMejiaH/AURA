from __future__ import annotations

from aura.autonomy import AutonomyModule
from aura.core import AURA, AURABootOptions, SystemState
from aura.events import GoalAchieved, GoalPrioritized, GoalSet, LongPlanGenerated


def test_autonomy_module_integration(tmp_path):
    options = AURABootOptions(
        enable_scheduler=False,
        enable_health_monitor=False,
        enable_cwm=True,
        enable_cognition=True,
        enable_audio=True,
        enable_vision=True,
        enable_memory=True,
        enable_tools=True,
        enable_robotics=True,
        enable_autonomy=True,
    )
    aura = AURA(options=options)
    aura.config.set("cwm.storage_path", str(tmp_path / "cwm.json"))
    aura.boot()

    assert aura.state == SystemState.RUNNING

    autonomy_mod = aura.module_manager.get("autonomy")
    assert autonomy_mod is not None
    assert isinstance(autonomy_mod, AutonomyModule)

    plan_events: list[LongPlanGenerated] = []
    prioritized_events: list[GoalPrioritized] = []

    aura.subscribe("LongPlanGenerated", lambda e: plan_events.append(e))
    aura.subscribe("GoalPrioritized", lambda e: prioritized_events.append(e))

    # Publish GoalSet event
    aura.publish(GoalSet(description="Explorar nuevo mapa de oficina"))

    assert len(plan_events) == 1
    assert plan_events[0].subgoal_count == 3

    assert len(prioritized_events) == 1

    active_goals = autonomy_mod.goals.get_active_goals()
    assert len(active_goals) == 1

    # Complete goal
    aura.publish(GoalAchieved(goal_id=active_goals[0].goal_id))
    assert active_goals[0].status == "achieved"
    assert autonomy_mod.learning.policy_version == 1.1

    aura.shutdown(wait=True)
    assert aura.state == SystemState.STOPPED
