from __future__ import annotations

from aura.events import EventBus, NavigationTargetReached, ObjectManipulated
from aura.robotics import GraspCommand, MockManipulator, MockNavigationSystem, Waypoint


def test_navigation_system_and_events():
    bus = EventBus()
    nav = MockNavigationSystem(event_bus=bus)

    nav_events: list[NavigationTargetReached] = []
    bus.subscribe("NavigationTargetReached", lambda e: nav_events.append(e))

    wp = Waypoint(x=10.5, y=5.0)
    res = nav.navigate_to(wp)

    assert res is True
    assert nav.current_position.x == 10.5
    assert len(nav_events) == 1
    assert nav_events[0].waypoint_x == 10.5


def test_manipulator_system_and_events():
    bus = EventBus()
    manipulator = MockManipulator(event_bus=bus)

    manip_events: list[ObjectManipulated] = []
    bus.subscribe("ObjectManipulated", lambda e: manip_events.append(e))

    cmd = GraspCommand(target_object_id="cup_01")
    assert manipulator.grasp_object(cmd) is True
    assert "cup_01" in manipulator.grasped_objects

    assert manipulator.release_object("cup_01") is True
    assert "cup_01" not in manipulator.grasped_objects

    assert len(manip_events) == 2
    assert manip_events[0].action == "grasp"
    assert manip_events[1].action == "release"
