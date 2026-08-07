from __future__ import annotations

from aura.audio import SilenceDetector
from aura.events import EventBus, SilenceDetected


def test_silence_detector_threshold_and_events():
    bus = EventBus()
    detector = SilenceDetector(silence_threshold_seconds=1.0, event_bus=bus)

    events: list[SilenceDetected] = []
    bus.subscribe("SilenceDetected", lambda e: events.append(e))

    # Below threshold -> no event
    assert detector.process_silence_duration(0.5) is False
    assert len(events) == 0

    # Above threshold -> event triggered
    assert detector.process_silence_duration(1.2) is True
    assert len(events) == 1
    assert events[0].duration_seconds == 1.2
