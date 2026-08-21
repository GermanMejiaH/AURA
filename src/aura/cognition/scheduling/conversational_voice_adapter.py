from __future__ import annotations

import time
from dataclasses import dataclass, field

from aura.audio.stt import MockSTTProvider, STTProvider
from aura.audio.tts import MockTTSProvider, TTSProvider
from aura.audio.types import AudioData, VoiceTurnMetrics
from aura.logging import get_logger

from .conversational_runtime import ConversationalRuntime, ConversationalTurnResult

logger = get_logger("ConversationalVoiceAdapter")


@dataclass
class VoiceTurnResult:
    """Result emitted by ConversationalVoiceAdapter for a voice audio turn."""

    recognized_text: str
    response_text: str
    audio_output: bytes
    conversational_turn_result: ConversationalTurnResult | None = None
    duration_seconds: float = 0.0
    metrics: VoiceTurnMetrics = field(default_factory=VoiceTurnMetrics)


class ConversationalVoiceAdapter:
    """Thin adapter bridging voice audio (STT/TTS) with ConversationalRuntime.

    Notice: This adapter has ZERO executive authority. It translates audio input to text,
    delegates execution exclusively to ConversationalRuntime (which dispatches to Stage 16),
    and synthesizes the grounded natural response into speech audio.
    """

    def __init__(
        self,
        conversational_runtime: ConversationalRuntime,
        stt_provider: STTProvider | None = None,
        tts_provider: TTSProvider | None = None,
    ) -> None:
        self.conversational_runtime = conversational_runtime
        self.stt = stt_provider or MockSTTProvider()
        self.tts = tts_provider or MockTTSProvider()

    def process_voice_turn(
        self,
        audio_input: AudioData | bytes,
        session_id: str = "default_session",
        user_id: str = "user",
        playback: bool = False,
    ) -> VoiceTurnResult:
        """Processes an audio voice turn: Audio -> STT -> ConversationalRuntime -> TTS."""
        turn_start = time.perf_counter()
        capture_dur = 0.0

        if isinstance(audio_input, AudioData):
            capture_dur = audio_input.duration_seconds

        # 1. Speech-to-Text Transcription
        t0 = time.perf_counter()
        try:
            stt_res = self.stt.transcribe(audio_input)
            recognized_text = stt_res.text.strip()
        except Exception as exc:
            logger.warning(f"STT transcription failed: {exc}")
            recognized_text = ""
        stt_dur = time.perf_counter() - t0

        if not recognized_text:
            total_dur = time.perf_counter() - turn_start
            metrics = VoiceTurnMetrics(
                capture_sec=capture_dur,
                stt_sec=stt_dur,
                cognition_sec=0.0,
                tts_sec=0.0,
                playback_sec=0.0,
                total_sec=total_dur,
            )
            return VoiceTurnResult(
                recognized_text="",
                response_text="No se reconoció ninguna entrada de voz.",
                audio_output=b"",
                conversational_turn_result=None,
                duration_seconds=total_dur,
                metrics=metrics,
            )

        # 2. Conversational Turn Processing (Routes to ConversationalRuntime -> Stage 16)
        t0 = time.perf_counter()
        conv_res = self.conversational_runtime.process_turn(
            conversation_id=session_id,
            user_input=recognized_text,
        )
        response_text = conv_res.natural_response
        cog_dur = time.perf_counter() - t0

        # 3. Text-to-Speech Synthesis
        t0 = time.perf_counter()
        audio_bytes = b""
        try:
            tts_res = self.tts.synthesize(response_text)
            audio_bytes = tts_res.audio_bytes
        except Exception as exc:
            logger.warning(f"TTS synthesis failed: {exc}")
        tts_dur = time.perf_counter() - t0

        total_dur = time.perf_counter() - turn_start
        metrics = VoiceTurnMetrics(
            capture_sec=capture_dur,
            stt_sec=stt_dur,
            cognition_sec=cog_dur,
            tts_sec=tts_dur,
            playback_sec=0.0,
            total_sec=total_dur,
        )

        return VoiceTurnResult(
            recognized_text=recognized_text,
            response_text=response_text,
            audio_output=audio_bytes,
            conversational_turn_result=conv_res,
            duration_seconds=total_dur,
            metrics=metrics,
        )
