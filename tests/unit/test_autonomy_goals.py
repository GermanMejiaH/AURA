from __future__ import annotations

from aura.autonomy import GoalManager
from aura.events import EventBus, GoalStatusChanged


def test_goal_manager_lifecycle_and_events():
    bus = EventBus()
    goals = GoalManager(event_bus=bus)

    status_events: list[GoalStatusChanged] = []
    bus.subscribe("GoalStatusChanged", lambda e: status_events.append(e))

    g = goals.create_goal(description="Organizar espacio de trabajo", priority=2.0)
    assert g.description == "Organizar espacio de trabajo"
    assert g.status == "pending"

    active_goals = goals.get_active_goals()
    assert len(active_goals) == 1
    assert active_goals[0].goal_id == g.goal_id

    assert goals.update_status(g.goal_id, "active") is True
    assert g.status == "active"

    assert len(status_events) == 2  # 1 from creation + 1 from update
    assert status_events[0].status == "pending"
    assert status_events[1].status == "active"
