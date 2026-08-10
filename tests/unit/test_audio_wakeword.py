from __future__ import annotations

from aura.audio import MockWakeWordDetector


def test_wakeword_detector_lifecycle_and_trigger():
    detector = MockWakeWordDetector()

    assert detector.is_active() is False
    detector.start()
    assert detector.is_active() is True

    res = detector.trigger(keyword="aura", confidence=0.99)
    assert res.detected is True
    assert res.keyword == "aura"

    detector.stop()
    assert detector.is_active() is False
