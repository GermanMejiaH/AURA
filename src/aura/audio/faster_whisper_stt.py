from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING, Any

from .stt import STTProvider, STTResult

if TYPE_CHECKING:
    from ..events import EventBus
    from ..memory.preferences import UserPreferencesMemory


class FasterWhisperSTTProvider(STTProvider):
    """Real Speech-to-Text provider using Faster Whisper with adaptive vocabulary learning."""

    def __init__(
        self,
        model_size_or_path: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        default_transcript: str = "",
        initial_prompt: str = "Hola AURA, asistente cognitivo autónomo AURA.",
        vad_filter: bool = False,
        event_bus: EventBus | None = None,
        preferences_memory: UserPreferencesMemory | None = None,
    ) -> None:
        self.model_size_or_path = model_size_or_path
        self.device = device
        self.compute_type = compute_type
        self.default_transcript = default_transcript
        self.initial_prompt = initial_prompt
        self.vad_filter = vad_filter
        self.event_bus = event_bus
        self.preferences_memory = preferences_memory
        self._model: Any = None
        self._custom_vocabulary: set[str] = set()

    def add_vocabulary_word(self, word: str) -> None:
        """Adds a custom word to the adaptive speech dictionary."""
        cleaned = word.strip()
        if cleaned:
            self._custom_vocabulary.add(cleaned)
            if self.preferences_memory is not None:
                current = self.preferences_memory.get_preference("speech_vocabulary", default="")
                vocab_list = [w.strip() for w in current.split(",") if w.strip()] if current else []
                if cleaned not in vocab_list:
                    vocab_list.append(cleaned)
                    self.preferences_memory.set_preference(
                        "speech_vocabulary", ", ".join(vocab_list), category="speech"
                    )

    def _get_effective_prompt(self) -> str:
        prompt = self.initial_prompt
        # Pull adaptive vocabulary from memory if available
        if self.preferences_memory is not None:
            saved_vocab = self.preferences_memory.get_preference("speech_vocabulary", default="")
            if saved_vocab:
                prompt = f"{prompt} Vocabulario adaptativo del usuario: {saved_vocab}."
        elif self._custom_vocabulary:
            custom_str = ", ".join(sorted(self._custom_vocabulary))
            prompt = f"{prompt} Vocabulario adaptativo: {custom_str}."
        return prompt

    def _get_model(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]

            self._model = WhisperModel(
                self.model_size_or_path,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "es",
    ) -> STTResult:
        model = self._get_model()

        # Handle raw audio bytes or file path
        if not audio_bytes:
            return STTResult(
                text=self.default_transcript,
                confidence=0.0,
                language=language,
            )

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            effective_prompt = self._get_effective_prompt()
            kwargs: dict[str, Any] = {"language": language}
            if effective_prompt:
                kwargs["initial_prompt"] = effective_prompt
            if self.vad_filter:
                kwargs["vad_filter"] = True

            segments, info = model.transcribe(tmp_path, **kwargs)
            segment_list = list(segments)
            transcript = " ".join([s.text.strip() for s in segment_list]).strip()
            if not transcript and self.default_transcript:
                transcript = self.default_transcript
            confidence = (
                sum(getattr(s, "avg_logprob", 0.0) for s in segment_list) / len(segment_list)
                if segment_list
                else 0.95
            )
            detected_lang = info.language if hasattr(info, "language") else language
        finally:
            import os

            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        result = STTResult(
            text=transcript,
            confidence=confidence,
            language=detected_lang,
        )

        if self.event_bus is not None and result.text:
            from ..events import SpeechRecognized

            self.event_bus.publish(
                SpeechRecognized(
                    source="FasterWhisperSTTProvider",
                    text=result.text,
                    confidence=result.confidence,
                    language=result.language,
                )
            )

        return result
