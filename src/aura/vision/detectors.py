from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus
    from .camera import FrameData


@dataclass
class DetectedPerson:
    person_id: str = "person_01"
    confidence: float = 0.95
    bounding_box: tuple[int, int, int, int] = (0, 0, 100, 200)


@dataclass
class DetectedObject:
    label: str = "laptop"
    confidence: float = 0.90
    bounding_box: tuple[int, int, int, int] = (10, 10, 50, 50)


@dataclass
class DetectedFace:
    name: str = "Andres"
    confidence: float = 0.98
    bounding_box: tuple[int, int, int, int] = (20, 20, 40, 40)


@dataclass
class OCRResult:
    text: str = ""
    confidence: float = 0.90


@dataclass
class VisualAnalysisResult:
    persons: list[DetectedPerson] = field(default_factory=list)
    objects: list[DetectedObject] = field(default_factory=list)
    faces: list[DetectedFace] = field(default_factory=list)
    ocr_texts: list[OCRResult] = field(default_factory=list)


# Interfaces
class PersonDetector(ABC):
    @abstractmethod
    def detect_persons(self, frame: FrameData) -> list[DetectedPerson]:
        ...


class ObjectDetector(ABC):
    @abstractmethod
    def detect_objects(self, frame: FrameData) -> list[DetectedObject]:
        ...


class FaceRecognizer(ABC):
    @abstractmethod
    def recognize_faces(self, frame: FrameData) -> list[DetectedFace]:
        ...


class OCRProcessor(ABC):
    @abstractmethod
    def extract_text(self, frame: FrameData) -> list[OCRResult]:
        ...


# Mock Implementations
class MockPersonDetector(PersonDetector):
    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def detect_persons(self, frame: FrameData) -> list[DetectedPerson]:
        person = DetectedPerson(person_id="user_01", confidence=0.96)
        if self.event_bus is not None:
            from ..events import PersonDetected

            self.event_bus.publish(
                PersonDetected(
                    source="MockPersonDetector",
                    person_id=person.person_id,
                    confidence=person.confidence,
                    bounding_box=person.bounding_box,
                )
            )
        return [person]


class MockObjectDetector(ObjectDetector):
    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def detect_objects(self, frame: FrameData) -> list[DetectedObject]:
        obj1 = DetectedObject(label="laptop", confidence=0.92)
        obj2 = DetectedObject(label="desk", confidence=0.88)
        if self.event_bus is not None:
            from ..events import ObjectDetected

            for obj in (obj1, obj2):
                self.event_bus.publish(
                    ObjectDetected(
                        source="MockObjectDetector",
                        label=obj.label,
                        confidence=obj.confidence,
                        bounding_box=obj.bounding_box,
                    )
                )
        return [obj1, obj2]


class MockFaceRecognizer(FaceRecognizer):
    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def recognize_faces(self, frame: FrameData) -> list[DetectedFace]:
        face = DetectedFace(name="Andres", confidence=0.97)
        if self.event_bus is not None:
            from ..events import FaceRecognized

            self.event_bus.publish(
                FaceRecognized(
                    source="MockFaceRecognizer",
                    name=face.name,
                    confidence=face.confidence,
                )
            )
        return [face]


class MockOCRProcessor(OCRProcessor):
    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def extract_text(self, frame: FrameData) -> list[OCRResult]:
        ocr = OCRResult(text="AURA Architecture V1.0", confidence=0.94)
        if self.event_bus is not None:
            from ..events import TextRecognized

            self.event_bus.publish(
                TextRecognized(
                    source="MockOCRProcessor",
                    text=ocr.text,
                    confidence=ocr.confidence,
                )
            )
        return [ocr]
