from __future__ import annotations

from aura.audio import MockWakeWordDetector
from aura.events import EventBus, WakeWordDetected


def test_wakeword_detector_lifecycle_and_trigger():
    bus = EventBus()
    detector = MockWakeWordDetector(event_bus=bus)

    assert detector.is_active() is False
    detector.start()
    assert detector.is_active() is True

    events: list[WakeWordDetected] = []
    bus.subscribe("WakeWordDetected", lambda e: events.append(e))

    res = detector.trigger(keyword="aura", confidence=0.99)
    assert res.detected is True
    assert res.keyword == "aura"

    assert len(events) == 1
    assert events[0].keyword == "aura"

    detector.stop()
    assert detector.is_active() is False
