from __future__ import annotations

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import EventBus
from ..logging import get_logger
from ..modules.base import BaseModule
from ..world import CognitiveWorldModel, Entity, EntityType, Relation, RelationType
from .camera import CameraProvider, MockCameraProvider
from .detectors import (
    FaceRecognizer,
    MockFaceRecognizer,
    MockObjectDetector,
    MockOCRProcessor,
    MockPersonDetector,
    ObjectDetector,
    OCRProcessor,
    PersonDetector,
    VisualAnalysisResult,
)


class VisionModule(BaseModule):
    """Core module responsible for visual perception, object/person detection & CWM integration."""

    name = "vision"
    description = "Vision System - Frame Capture, Object/Person Detection & CWM Sync"
    priority = 35

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        container: DependencyContainer | None = None,
        event_bus: EventBus | None = None,
        camera_provider: CameraProvider | None = None,
        person_detector: PersonDetector | None = None,
        object_detector: ObjectDetector | None = None,
        face_recognizer: FaceRecognizer | None = None,
        ocr_processor: OCRProcessor | None = None,
    ) -> None:
        super().__init__(config, container, event_bus)
        self.camera = (
            camera_provider
            if camera_provider is not None
            else MockCameraProvider(event_bus=event_bus)
        )
        self.person_detector = (
            person_detector
            if person_detector is not None
            else MockPersonDetector(event_bus=event_bus)
        )
        self.object_detector = (
            object_detector
            if object_detector is not None
            else MockObjectDetector(event_bus=event_bus)
        )
        self.face_recognizer = (
            face_recognizer
            if face_recognizer is not None
            else MockFaceRecognizer(event_bus=event_bus)
        )
        self.ocr_processor = (
            ocr_processor
            if ocr_processor is not None
            else MockOCRProcessor(event_bus=event_bus)
        )

    def on_initialize(self) -> None:
        logger = get_logger("VisionModule")

        # Register IoC instances
        if self._container is not None:
            self._container.register(MockCameraProvider, instance=self.camera)
            self._container.register(MockPersonDetector, instance=self.person_detector)
            self._container.register(MockObjectDetector, instance=self.object_detector)
            self._container.register(MockFaceRecognizer, instance=self.face_recognizer)
            self._container.register(MockOCRProcessor, instance=self.ocr_processor)

        logger.info("VisionModule initialized")

    def on_start(self) -> None:
        self.camera.start()

    def on_stop(self) -> None:
        self.camera.stop()

    def process_visual_scene(self) -> VisualAnalysisResult:
        """Captures a frame, runs all visual detectors, updates CWM and returns result."""
        logger = get_logger("VisionModule")
        frame = self.camera.capture_frame()

        persons = self.person_detector.detect_persons(frame)
        objects = self.object_detector.detect_objects(frame)
        faces = self.face_recognizer.recognize_faces(frame)
        ocrs = self.ocr_processor.extract_text(frame)

        result = VisualAnalysisResult(
            persons=persons,
            objects=objects,
            faces=faces,
            ocr_texts=ocrs,
        )

        # Sync detected entities to Cognitive World Model (CWM)
        if self._container is not None and self._container.has(CognitiveWorldModel):
            cwm = self._container.resolve(CognitiveWorldModel)
            self._sync_visual_result_to_cwm(cwm, result)

        if self._event_bus is not None:
            from ..events import VisualSceneProcessed

            self.publish(
                VisualSceneProcessed(
                    source="VisionModule",
                    objects_count=len(objects),
                    persons_count=len(persons),
                    faces_count=len(faces),
                )
            )

        logger.info(
            f"Visual scene processed ({len(persons)} persons, "
            f"{len(objects)} objects, {len(faces)} faces)"
        )
        return result

    def _sync_visual_result_to_cwm(
        self,
        cwm: CognitiveWorldModel,
        result: VisualAnalysisResult,
    ) -> None:
        for p in result.persons:
            cwm.add_entity(
                Entity(
                    name=f"Person_{p.person_id}",
                    type=EntityType.PERSON,
                    attributes={"confidence": p.confidence},
                )
            )
        for obj in result.objects:
            cwm.add_entity(
                Entity(
                    name=f"Object_{obj.label}",
                    type=EntityType.OBJECT,
                    attributes={"confidence": obj.confidence},
                )
            )
        for face in result.faces:
            user_entity = Entity(
                name=face.name,
                type=EntityType.PERSON,
                attributes={"recognized": True},
            )
            cwm.add_entity(user_entity)

            # Relate face entity to aura
            aura_entity = cwm.get_entity_by_name("AURA")
            if aura_entity:
                cwm.add_relation(
                    Relation(
                        source_id=aura_entity.id,
                        target_id=user_entity.id,
                        relation_type=RelationType.OBSERVES,
                    )
                )
