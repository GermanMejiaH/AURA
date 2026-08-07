from __future__ import annotations

from .camera import CameraProvider, FrameData, MockCameraProvider
from .detectors import (
    DetectedFace,
    DetectedObject,
    DetectedPerson,
    FaceRecognizer,
    MockFaceRecognizer,
    MockObjectDetector,
    MockOCRProcessor,
    MockPersonDetector,
    ObjectDetector,
    OCRProcessor,
    OCRResult,
    PersonDetector,
    VisualAnalysisResult,
)
from .module import VisionModule

__all__ = [
    "CameraProvider",
    "DetectedFace",
    "DetectedObject",
    "DetectedPerson",
    "FaceRecognizer",
    "FrameData",
    "MockCameraProvider",
    "MockFaceRecognizer",
    "MockOCRProcessor",
    "MockObjectDetector",
    "MockPersonDetector",
    "OCRProcessor",
    "OCRResult",
    "ObjectDetector",
    "PersonDetector",
    "VisionModule",
    "VisualAnalysisResult",
]
