from __future__ import annotations

from aura.autonomy import AutonomousGoal, LearningEngine, LongHorizonPlanner, PriorityEngine
from aura.events import EventBus, GoalPrioritized, LongPlanGenerated, PolicyUpdated


def test_priority_engine_and_events():
    bus = EventBus()
    pe = PriorityEngine(event_bus=bus)

    p_events: list[GoalPrioritized] = []
    bus.subscribe("GoalPrioritized", lambda e: p_events.append(e))

    g1 = AutonomousGoal(description="Baja prioridad", priority=1.0)
    g2 = AutonomousGoal(description="Alta prioridad", priority=5.0)

    ranked = pe.rank_goals([g1, g2])
    assert ranked[0].goal_id == g2.goal_id
    assert len(p_events) == 1
    assert p_events[0].goal_id == g2.goal_id


def test_long_horizon_planner_and_events():
    bus = EventBus()
    planner = LongHorizonPlanner(event_bus=bus)

    plan_events: list[LongPlanGenerated] = []
    bus.subscribe("LongPlanGenerated", lambda e: plan_events.append(e))

    g = AutonomousGoal(description="Construir mapa del entorno")
    subgoals = planner.generate_plan(g)

    assert len(subgoals) == 3
    assert len(g.subgoals) == 3
    assert len(plan_events) == 1
    assert plan_events[0].subgoal_count == 3


def test_learning_engine_and_events():
    bus = EventBus()
    learning = LearningEngine(event_bus=bus)

    policy_events: list[PolicyUpdated] = []
    bus.subscribe("PolicyUpdated", lambda e: policy_events.append(e))

    learning.record_feedback(goal_id="g1", success=True)
    assert learning.policy_version == 1.1
    assert len(policy_events) == 1
    assert policy_events[0].version == "1.1"
