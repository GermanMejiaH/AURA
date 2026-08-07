from __future__ import annotations

from aura.cognition import (
    ActionCoordinator,
    Decision,
    Intent,
    Planner,
)
from aura.events import EventBus


def test_planner_creates_executable_plan():
    planner = Planner()
    decision = Decision(
        intent=Intent(
            name="turn_on_lights",
            target="living_room",
            parameters={
                "suggested_actions": [
                    {"name": "check_status", "type": "query", "target": "lights"},
                    {"name": "send_signal", "type": "iot", "target": "living_room_light"},
                ]
            },
        )
    )

    plan = planner.create_plan(decision)
    assert plan.goal == "turn_on_lights"
    assert len(plan.steps) == 2
    assert plan.steps[0].name == "check_status"


def test_action_coordinator_executes_plan_steps():
    bus = EventBus()
    coordinator = ActionCoordinator(event_bus=bus)
    planner = Planner()
    decision = Decision(intent=Intent(name="general_response"))

    plan = planner.create_plan(decision)
    results = coordinator.execute_plan(plan)

    assert len(results) == 1
    assert results[0].success is True
    assert plan.is_complete is True
