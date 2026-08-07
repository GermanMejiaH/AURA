from __future__ import annotations

from aura.core import AURA, AURABootOptions, SystemState
from aura.events import ActionDispatched, MotorMoved, NavigationTargetReached
from aura.robotics import RoboticsModule


def test_robotics_module_integration(tmp_path):
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
    )
    aura = AURA(options=options)
    aura.config.set("cwm.storage_path", str(tmp_path / "cwm.json"))
    aura.boot()

    assert aura.state == SystemState.RUNNING

    robotics_mod = aura.module_manager.get("robotics")
    assert robotics_mod is not None
    assert isinstance(robotics_mod, RoboticsModule)

    motor_events: list[MotorMoved] = []
    nav_events: list[NavigationTargetReached] = []

    aura.subscribe("MotorMoved", lambda e: motor_events.append(e))
    aura.subscribe("NavigationTargetReached", lambda e: nav_events.append(e))

    # Publish motor action
    aura.publish(
        ActionDispatched(action_type="move_joint", payload={"joint_id": "elbow", "position": 0.78})
    )

    # Publish navigation action
    aura.publish(ActionDispatched(action_type="navigate", payload={"x": 5.0, "y": 12.0}))

    assert len(motor_events) == 1
    assert motor_events[0].joint_id == "elbow"
    assert motor_events[0].position == 0.78

    assert len(nav_events) == 1
    assert nav_events[0].waypoint_x == 5.0

    aura.shutdown(wait=True)
    assert aura.state == SystemState.STOPPED
