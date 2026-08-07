from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import Event, EventBus
from ..logging import get_logger
from ..modules.base import BaseModule
from .silence import SilenceDetector
from .stt import MockSTTProvider, STTProvider
from .tts import MockTTSProvider, TTSProvider
from .wakeword import MockWakeWordDetector, WakeWordDetector

if TYPE_CHECKING:
    pass


class AudioModule(BaseModule):
    """Core module responsible for voice interactions, wake word, STT, TTS & audio lifecycle."""

    name = "audio"
    description = "Audio System - Voice Input/Output, Wake Word, STT & TTS"
    priority = 30

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        container: DependencyContainer | None = None,
        event_bus: EventBus | None = None,
        wakeword_detector: WakeWordDetector | None = None,
        stt_provider: STTProvider | None = None,
        tts_provider: TTSProvider | None = None,
    ) -> None:
        super().__init__(config, container, event_bus)
        self.wakeword = (
            wakeword_detector
            if wakeword_detector is not None
            else MockWakeWordDetector(event_bus=event_bus)
        )
        self.stt = (
            stt_provider if stt_provider is not None else MockSTTProvider(event_bus=event_bus)
        )
        self.tts = (
            tts_provider if tts_provider is not None else MockTTSProvider(event_bus=event_bus)
        )
        self.silence_detector = SilenceDetector(event_bus=event_bus)

    def on_initialize(self) -> None:
        logger = get_logger("AudioModule")

        # Register IoC instances
        if self._container is not None:
            self._container.register(MockWakeWordDetector, instance=self.wakeword)
            self._container.register(MockSTTProvider, instance=self.stt)
            self._container.register(MockTTSProvider, instance=self.tts)
            self._container.register(SilenceDetector, instance=self.silence_detector)

        # Event Subscriptions
        self.subscribe("WakeWordDetected", self._on_wakeword_detected)
        self.subscribe("ActionDispatched", self._on_action_dispatched)

        logger.info("AudioModule initialized")

    def on_start(self) -> None:
        self.wakeword.start()

    def on_stop(self) -> None:
        self.wakeword.stop()

    def trigger_voice_interaction(self, voice_text: str = "Hola AURA") -> str:
        """Simulates or processes a complete voice interaction turn."""
        logger = get_logger("AudioModule")
        logger.info(f"Voice interaction triggered with input text: '{voice_text}'")

        # 1. Transcribe STT
        stt_res = self.stt.transcribe(voice_text.encode("utf-8"))

        # 2. Forward to CognitionModule if available in container
        if self._container is not None:
            from ..cognition import CognitionModule

            if self._container.has(CognitionModule):
                cog = self._container.resolve(CognitionModule)
                reasoning = cog.process_cognitive_cycle(stt_res.text)

                # 3. Synthesize TTS response
                tts_res = self.tts.synthesize(reasoning.summary)
                return tts_res.text

        # Fallback TTS
        tts_res = self.tts.synthesize(f"Procesado: {stt_res.text}")
        return tts_res.text

    def _on_wakeword_detected(self, event: Event) -> None:
        logger = get_logger("AudioModule")
        logger.info(f"Wake word detected ({event.payload.get('keyword', 'aura')})")

        # Request CognitiveStateMachine transition to LISTENING if container has it
        if self._container is not None:
            from ..cognition import CognitiveState, CognitiveStateMachine

            if self._container.has(CognitiveStateMachine):
                sm = self._container.resolve(CognitiveStateMachine)
                sm.transition_to(CognitiveState.LISTENING, reason="wakeword_detected")

    def _on_action_dispatched(self, event: Event) -> None:
        action_type = event.payload.get("action_type")
        target = event.payload.get("target", "")

        if action_type == "speak" or action_type == "tts":
            text = event.payload.get("text", target)
            if text:
                self.tts.synthesize(text)
