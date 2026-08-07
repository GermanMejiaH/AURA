from __future__ import annotations

from aura.events import EventBus, FrameCaptured
from aura.vision import MockCameraProvider


def test_camera_provider_lifecycle_and_frame_capture():
    bus = EventBus()
    camera = MockCameraProvider(event_bus=bus)

    assert camera.is_active() is False
    camera.start()
    assert camera.is_active() is True

    events: list[FrameCaptured] = []
    bus.subscribe("FrameCaptured", lambda e: events.append(e))

    frame = camera.capture_frame()
    assert frame.width == 640
    assert frame.height == 480
    assert len(frame.image_bytes) > 0

    assert len(events) == 1
    assert events[0].width == 640

    camera.stop()
    assert camera.is_active() is False
