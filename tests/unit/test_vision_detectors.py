from __future__ import annotations

from aura.events import EventBus, FaceRecognized, ObjectDetected, PersonDetected, TextRecognized
from aura.vision import (
    FrameData,
    MockFaceRecognizer,
    MockObjectDetector,
    MockOCRProcessor,
    MockPersonDetector,
)


def test_vision_detectors():
    bus = EventBus()
    person_det = MockPersonDetector(event_bus=bus)
    object_det = MockObjectDetector(event_bus=bus)
    face_rec = MockFaceRecognizer(event_bus=bus)
    ocr_proc = MockOCRProcessor(event_bus=bus)

    frame = FrameData(image_bytes=b"dummy")

    person_events: list[PersonDetected] = []
    object_events: list[ObjectDetected] = []
    face_events: list[FaceRecognized] = []
    ocr_events: list[TextRecognized] = []

    bus.subscribe("PersonDetected", lambda e: person_events.append(e))
    bus.subscribe("ObjectDetected", lambda e: object_events.append(e))
    bus.subscribe("FaceRecognized", lambda e: face_events.append(e))
    bus.subscribe("TextRecognized", lambda e: ocr_events.append(e))

    persons = person_det.detect_persons(frame)
    objects = object_det.detect_objects(frame)
    faces = face_rec.recognize_faces(frame)
    texts = ocr_proc.extract_text(frame)

    assert len(persons) == 1
    assert len(objects) == 2
    assert len(faces) == 1
    assert len(texts) == 1

    assert len(person_events) == 1
    assert len(object_events) == 2
    assert len(face_events) == 1
    assert len(ocr_events) == 1
