from __future__ import annotations

from aura.events import EmergencyStopTriggered, EventBus, SafetyAlert
from aura.robotics import SafetySystem


def test_safety_system_e_stop_and_alerts():
    bus = EventBus()
    safety = SafetySystem(event_bus=bus)

    e_stop_events: list[EmergencyStopTriggered] = []
    alert_events: list[SafetyAlert] = []

    bus.subscribe("EmergencyStopTriggered", lambda e: e_stop_events.append(e))
    bus.subscribe("SafetyAlert", lambda e: alert_events.append(e))

    assert safety.is_emergency_stopped is False

    safety.report_hazard("Obstáculo cercano", level="WARNING")
    assert len(alert_events) == 1
    assert alert_events[0].message == "Obstáculo cercano"

    safety.trigger_emergency_stop(reason="obstruction")
    assert safety.is_emergency_stopped is True
    assert len(e_stop_events) == 1
    assert e_stop_events[0].reason == "obstruction"

    safety.reset_emergency_stop()
    assert safety.is_emergency_stopped is False
