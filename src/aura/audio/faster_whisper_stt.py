from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING, Any

from .stt import STTProvider, STTResult
from .types import AudioData

if TYPE_CHECKING:
    from ..config import ConfigurationManager
    from ..memory.preferences import UserPreferencesMemory


class FasterWhisperSTTProvider(STTProvider):
    """Real Speech-to-Text provider using Faster Whisper with adaptive vocabulary learning."""

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        model_size_or_path: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        default_transcript: str = "",
        initial_prompt: str = "",
        vad_filter: bool = False,
        preferences_memory: UserPreferencesMemory | None = None,
    ) -> None:
        self.config = config
        self.model_size_or_path = (
            model_size_or_path
            if model_size_or_path is not None
            else (config.get_typed("stt.model", str, "small") if config else "small")
        )
        self.device = (
            device
            if device is not None
            else (config.get_typed("stt.device", str, "cpu") if config else "cpu")
        )
        self.compute_type = (
            compute_type
            if compute_type is not None
            else (config.get_typed("stt.compute_type", str, "int8") if config else "int8")
        )
        self.default_transcript = default_transcript
        self.initial_prompt = initial_prompt
        self.vad_filter = vad_filter
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

            from ..logging import get_logger

            logger = get_logger("FasterWhisperSTTProvider")
            target_device = self.device
            target_compute = self.compute_type

            if target_device in ("cuda", "auto"):
                try:
                    self._model = WhisperModel(
                        self.model_size_or_path,
                        device="cuda",
                        compute_type="float16" if target_compute == "float16" else "int8_float16",
                        cpu_threads=4,
                    )
                    logger.info(
                        f"FasterWhisper initialized on CUDA GPU [model={self.model_size_or_path}]"
                    )
                except Exception as exc:
                    logger.warning(
                        f"CUDA device unavailable or failed ({exc}). Falling back to CPU."
                    )
                    target_device = "cpu"
                    target_compute = "int8"
                    self._model = None

            if self._model is None:
                self._model = WhisperModel(
                    self.model_size_or_path,
                    device=target_device,
                    compute_type=target_compute,
                    cpu_threads=4,
                )
                logger.info(
                    f"FasterWhisper initialized on CPU [model={self.model_size_or_path}, "
                    f"compute_type={target_compute}]"
                )
        return self._model

    def transcribe(
        self,
        audio: AudioData | bytes,
        language: str = "es",
    ) -> STTResult:
        import re

        raw_bytes = audio.raw_data if isinstance(audio, AudioData) else audio

        # Handle raw audio bytes or file path
        if not raw_bytes:
            return STTResult(
                text=self.default_transcript,
                confidence=0.0,
                language=language,
            )

        model = self._get_model()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        try:
            effective_prompt = self._get_effective_prompt()
            kwargs: dict[str, Any] = {
                "language": language,
                "beam_size": 2,
                "best_of": 2,
            }
            if effective_prompt:
                kwargs["initial_prompt"] = effective_prompt
            if self.vad_filter:
                kwargs["vad_filter"] = True

            try:
                segments, info = model.transcribe(tmp_path, **kwargs)
                segment_list = list(segments)
            except Exception as exc:
                from ..logging import get_logger

                logger = get_logger("FasterWhisperSTTProvider")
                if self.device in ("cuda", "auto"):
                    logger.warning(
                        f"FasterWhisper CUDA execution failed ({exc}). Falling back to CPU..."
                    )
                    self.device = "cpu"
                    self.compute_type = "int8"
                    self._model = None
                    model = self._get_model()
                    segments, info = model.transcribe(tmp_path, **kwargs)
                    segment_list = list(segments)
                else:
                    logger.error(f"FasterWhisper transcription failed: {exc}")
                    return STTResult(text="", confidence=0.0, language=language)

            # Check no_speech_prob from Whisper model to reject silence hallucinations
            no_speech = getattr(info, "no_speech_prob", 0.0)
            if isinstance(no_speech, (float, int)) and no_speech > 0.45:
                return STTResult(text="", confidence=0.0, language=language)

            transcript = " ".join([s.text.strip() for s in segment_list]).strip()

            # Hallucination blacklist filter (common Whisper noise hallucination outputs)
            hallucinations = (
                "subtítulos",
                "gracias por ver",
                "suscríbete",
                "amén",
                "transcripción realizada",
                "comunidad de youtube",
                "continuará",
                "suscripciones",
                "gracias.",
                "audio",
            )
            clean_lower = transcript.lower().strip()
            if any(h in clean_lower for h in hallucinations) and len(transcript.split()) <= 4:
                transcript = ""

            if not transcript and self.default_transcript:
                transcript = self.default_transcript

            # Only fix targeted greeting misrecognitions of "AURA"
            if transcript:
                transcript = re.sub(
                    r"\b([Hh]ola)\s+(auda|aurora|aula|avra)\b",
                    r"\1 AURA",
                    transcript,
                    flags=re.IGNORECASE,
                )
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

        return STTResult(
            text=transcript,
            confidence=confidence,
            language=detected_lang,
        )
