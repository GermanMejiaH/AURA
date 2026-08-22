from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import (
    AudioPlaybackFinished,
    AudioPlaybackStarted,
    Event,
    EventBus,
    SpeechRecognized,
    SpeechSynthesized,
)
from ..logging import get_logger
from ..modules.base import BaseModule
from .input import AudioInputProvider, MockAudioInputProvider
from .output import AudioOutputProvider, MockAudioOutputProvider
from .silence import SilenceDetector
from .stt import MockSTTProvider, STTProvider
from .tts import MockTTSProvider, TTSProvider
from .types import AudioData, AudioTurnResult, VoiceTurnMetrics
from .wakeword import MockWakeWordDetector, WakeWordDetector

if TYPE_CHECKING:
    pass


class AudioModule(BaseModule):
    """Core module responsible for voice interactions, STT, TTS, input/output & audio lifecycle."""

    name = "audio"
    description = "Audio System - Voice Input/Output, Wake Word, STT & TTS"
    priority = 30

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        container: DependencyContainer | None = None,
        event_bus: EventBus | None = None,
        audio_input: AudioInputProvider | None = None,
        audio_output: AudioOutputProvider | None = None,
        wakeword_detector: WakeWordDetector | None = None,
        stt_provider: STTProvider | None = None,
        tts_provider: TTSProvider | None = None,
    ) -> None:
        super().__init__(config, container, event_bus)
        self.audio_input = audio_input if audio_input is not None else MockAudioInputProvider()
        self.audio_output = audio_output if audio_output is not None else MockAudioOutputProvider()
        self.wakeword = (
            wakeword_detector if wakeword_detector is not None else MockWakeWordDetector()
        )
        self.stt = stt_provider if stt_provider is not None else MockSTTProvider()
        self.tts = tts_provider if tts_provider is not None else MockTTSProvider()
        self.silence_detector = SilenceDetector(event_bus=event_bus)

    def on_initialize(self) -> None:
        logger = get_logger("AudioModule")

        # Register IoC instances
        if self._container is not None:
            self._container.register(MockWakeWordDetector, instance=self.wakeword)
            self._container.register(MockSTTProvider, instance=self.stt)
            self._container.register(MockTTSProvider, instance=self.tts)
            self._container.register(SilenceDetector, instance=self.silence_detector)
            self._container.register(AudioInputProvider, instance=self.audio_input)
            self._container.register(AudioOutputProvider, instance=self.audio_output)

        # Event Subscriptions
        self.subscribe("WakeWordDetected", self._on_wakeword_detected)
        self.subscribe("ActionDispatched", self._on_action_dispatched)

        logger.info("AudioModule initialized")

    def on_start(self) -> None:
        self.wakeword.start()

    def on_stop(self) -> None:
        self.wakeword.stop()
        self.audio_input.close()
        self.audio_output.close()

    def start_voice_capture(self, device: int | str | None = None) -> None:
        """Starts controlled audio capture (Push-to-Talk)."""
        target_dev = device
        if target_dev is None and self._config is not None:
            cfg_val = self._config.get("audio.input_device", "")
            if cfg_val:
                target_dev = cfg_val
        self.audio_input.start_capture(device=target_dev)

    def stop_voice_capture_and_process(
        self,
        playback: bool = True,
    ) -> AudioTurnResult:
        """Stops controlled audio capture and processes the conversational turn."""
        t_start = time.perf_counter()
        audio_data = self.audio_input.stop_capture()
        t_capture = time.perf_counter() - t_start

        return self.process_conversational_turn(
            audio_input=audio_data,
            playback=playback,
            capture_duration=t_capture,
        )

    def is_capturing_voice(self) -> bool:
        """Returns True if push-to-talk audio capture is active."""
        return self.audio_input.is_capturing()

    def process_conversational_turn(
        self,
        audio_input: AudioData | bytes,
        playback: bool = True,
        capture_duration: float = 0.0,
    ) -> AudioTurnResult:
        """Processes a conversational turn: Audio -> STT -> Cognition -> TTS -> Output Playback."""
        logger = get_logger("AudioModule")
        logger.info("Processing conversational audio turn...")

        turn_start = time.perf_counter()

        # If audio_input is AudioData with explicit duration, use it for capture duration if 0
        if isinstance(audio_input, AudioData) and capture_duration <= 0.0:
            capture_duration = audio_input.duration_seconds

        # 1. Speech-to-Text Transcription
        t0 = time.perf_counter()
        stt_res = self.stt.transcribe(audio_input)
        stt_duration = time.perf_counter() - t0

        # 2. Publish SpeechRecognized Event
        self.publish(
            SpeechRecognized(
                source="AudioModule",
                text=stt_res.text,
                confidence=stt_res.confidence,
                language=stt_res.language,
            )
        )

        # If transcript is empty, return early with metrics
        if not stt_res.text.strip():
            total_dur = time.perf_counter() - turn_start
            metrics = VoiceTurnMetrics(
                capture_sec=capture_duration,
                stt_sec=stt_duration,
                cognition_sec=0.0,
                tts_sec=0.0,
                playback_sec=0.0,
                total_sec=total_dur,
            )
            return AudioTurnResult(
                recognized_text="",
                response_text="",
                audio_output=b"",
                duration_seconds=total_dur,
                metrics=metrics,
            )

        # 3. Forward transcript to CognitionModule if available
        t0 = time.perf_counter()
        response_text = f"Procesado: {stt_res.text}"
        if self._container is not None:
            from ..cognition import CognitionModule

            if self._container.has(CognitionModule):
                cog = self._container.resolve(CognitionModule)
                reasoning = cog.process_cognitive_cycle(stt_res.text)
                response_text = reasoning.summary
        cog_duration = time.perf_counter() - t0

        # 4. Text-to-Speech Synthesis
        t0 = time.perf_counter()
        tts_res = self.tts.synthesize(response_text)
        tts_duration = time.perf_counter() - t0

        # 5. Audio Output Playback
        t0 = time.perf_counter()
        self.publish(
            SpeechSynthesized(
                source="AudioModule",
                text=tts_res.text,
                audio_bytes_length=len(tts_res.audio_bytes),
            )
        )
        self.publish(AudioPlaybackStarted(source="AudioModule", text=tts_res.text))

        if playback and tts_res.audio_bytes:
            self.audio_output.play(tts_res.audio_bytes)

        self.publish(AudioPlaybackFinished(source="AudioModule", text=tts_res.text))
        playback_duration = time.perf_counter() - t0

        total_duration = time.perf_counter() - turn_start

        metrics = VoiceTurnMetrics(
            capture_sec=capture_duration,
            stt_sec=stt_duration,
            cognition_sec=cog_duration,
            tts_sec=tts_duration,
            playback_sec=playback_duration,
            total_sec=total_duration,
        )

        logger.info(
            f"Voice turn completed: capture={metrics.capture_sec:.2f}s "
            f"stt={metrics.stt_sec:.2f}s cognition={metrics.cognition_sec:.2f}s "
            f"tts={metrics.tts_sec:.2f}s playback={metrics.playback_sec:.2f}s "
            f"total={metrics.total_sec:.2f}s"
        )

        return AudioTurnResult(
            recognized_text=stt_res.text,
            response_text=tts_res.text,
            audio_output=tts_res.audio_bytes,
            duration_seconds=total_duration,
            metrics=metrics,
        )

    def trigger_voice_interaction(self, voice_text: str = "Hola AURA") -> str:
        """Helper method to simulate a voice interaction using a text input hint."""
        audio_data = AudioData.create_mock(text=voice_text)
        turn_result = self.process_conversational_turn(audio_data, playback=False)
        return turn_result.response_text

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

        if action_type in ("speak", "tts"):
            text = str(event.payload.get("text", target))
            if text:
                res = self.tts.synthesize(text)
                if res.audio_bytes:
                    self.audio_output.play(res.audio_bytes)
