from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AudioData:
    """Encapsulates raw audio sample data along with audio parameters."""

    raw_data: bytes
    sample_rate: int = 16000
    channels: int = 1
    sample_format: str = "int16"
    duration_seconds: float = 0.0
    text_hint: str = ""

    def __post_init__(self) -> None:
        if self.duration_seconds <= 0.0 and self.sample_rate > 0:
            bytes_per_sample = 2 if self.sample_format == "int16" else 1
            frame_size = self.channels * bytes_per_sample
            if frame_size > 0 and len(self.raw_data) > 0:
                self.duration_seconds = len(self.raw_data) / (self.sample_rate * frame_size)
            else:
                self.duration_seconds = 1.0

    @classmethod
    def create_mock(cls, text: str = "Hola AURA", duration: float = 1.0) -> AudioData:
        """Helper factory to create mock AudioData with a text hint for tests."""
        dummy_pcm = b"\x00\x00" * int(16000 * duration)
        return cls(
            raw_data=dummy_pcm,
            sample_rate=16000,
            channels=1,
            sample_format="int16",
            duration_seconds=duration,
            text_hint=text,
        )


@dataclass
class VoiceTurnMetrics:
    """Metrics tracking execution time of each phase in a voice interaction turn."""

    capture_sec: float = 0.0
    stt_sec: float = 0.0
    context_sec: float = 0.0
    llm_sec: float = 0.0
    cognition_sec: float = 0.0
    tts_sec: float = 0.0
    playback_sec: float = 0.0
    total_sec: float = 0.0


@dataclass
class AudioTurnResult:
    """Result of a processed conversational audio turn."""

    recognized_text: str
    response_text: str
    audio_output: bytes | None = None
    duration_seconds: float = 0.0
    metrics: VoiceTurnMetrics = field(default_factory=VoiceTurnMetrics)
