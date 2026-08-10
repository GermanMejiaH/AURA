from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

from .wakeword import WakeWordDetector, WakeWordResult

if TYPE_CHECKING:
    pass


class WhisperWakeWordDetector(WakeWordDetector):
    """Wake Word Detector using Faster Whisper on short audio chunks.

    Continuously records short audio snippets (1-2 seconds) and checks
    if any configured wake keywords appear in the transcription.
    Fires WakeWordDetected event when detected.
    """

    DEFAULT_KEYWORDS: ClassVar[list[str]] = [
        "aura",
        "auda",
        "aurora",
        "aula",
        "hora",
        "laura",
        "ahora",
    ]

    def __init__(
        self,
        keywords: list[str] | None = None,
        model_size: str = "tiny",
        chunk_duration_sec: float = 1.5,
        on_detected: Callable[[WakeWordResult], None] | None = None,
    ) -> None:
        self.keywords = [k.lower() for k in (keywords or self.DEFAULT_KEYWORDS)]
        self.model_size = model_size
        self.chunk_duration_sec = chunk_duration_sec
        self.on_detected = on_detected

        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Begin background listening for the wake word."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop background wake word detection."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def is_active(self) -> bool:
        return self._running

    def _listen_loop(self) -> None:
        """Background thread: record short chunks and check for wake keywords."""
        from faster_whisper import WhisperModel  # type: ignore[import-untyped]

        from .microphone import MicrophoneRecorder

        recorder = MicrophoneRecorder(sample_rate=16000)
        model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

        while self._running:
            try:
                audio_bytes = recorder.record_bytes(duration_sec=self.chunk_duration_sec)
                if not audio_bytes:
                    continue

                result = self._check_for_keyword(model, audio_bytes)
                if result.detected:
                    self._fire_detected(result)

            except Exception:
                time.sleep(0.2)

    def _check_for_keyword(self, model: object, audio_bytes: bytes) -> WakeWordResult:
        """Transcribes chunk and checks for any configured keyword."""
        import os
        import tempfile
        from typing import Any

        wmodel: Any = model

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            segments, _ = wmodel.transcribe(
                tmp_path,
                language="es",
                initial_prompt="AURA, hora, ahora, laura.",
            )
            text = " ".join(s.text.strip() for s in segments).lower()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        for keyword in self.keywords:
            if keyword in text:
                return WakeWordResult(detected=True, keyword=keyword, confidence=0.90)

        return WakeWordResult(detected=False, keyword="", confidence=0.0)

    def _fire_detected(self, result: WakeWordResult) -> None:
        """Calls on_detected callback when wake word is detected."""
        if self.on_detected is not None:
            self.on_detected(result)
