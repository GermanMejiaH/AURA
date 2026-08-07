from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


@dataclass
class FrameData:
    image_bytes: bytes
    width: int = 640
    height: int = 480
    format: str = "jpeg"


class CameraProvider(ABC):
    """Abstract interface for Camera Providers (OpenCV, PiCamera, WebRTC)."""

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @abstractmethod
    def is_active(self) -> bool:
        ...

    @abstractmethod
    def capture_frame(self) -> FrameData:
        ...


class MockCameraProvider(CameraProvider):
    """Mock Camera Provider for testing and server environments."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def is_active(self) -> bool:
        return self._running

    def capture_frame(self) -> FrameData:
        fake_bytes = b"mock_frame_data_640x480"
        frame = FrameData(image_bytes=fake_bytes, width=640, height=480)

        if self.event_bus is not None:
            from ..events import FrameCaptured

            self.event_bus.publish(
                FrameCaptured(
                    source="MockCameraProvider",
                    width=frame.width,
                    height=frame.height,
                    frame_size_bytes=len(fake_bytes),
                )
            )

        return frame
