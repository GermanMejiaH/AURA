from __future__ import annotations

from .module import AudioModule
from .silence import SilenceDetector
from .stt import MockSTTProvider, STTProvider, STTResult
from .tts import MockTTSProvider, TTSProvider, TTSResult
from .wakeword import MockWakeWordDetector, WakeWordDetector, WakeWordResult

__all__ = [
    "AudioModule",
    "MockSTTProvider",
    "MockTTSProvider",
    "MockWakeWordDetector",
    "STTProvider",
    "STTResult",
    "SilenceDetector",
    "TTSProvider",
    "TTSResult",
    "WakeWordDetector",
    "WakeWordResult",
]
