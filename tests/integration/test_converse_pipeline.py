from __future__ import annotations

import io
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from aura import AURA, AURABootOptions
from aura.audio import FasterWhisperSTTProvider, MicrophoneRecorder
from aura.cognition import CognitionModule, LLMResponse
from aura.config import ConfigurationManager
from aura.memory import Fact, MemoryModule


def test_converse_end_to_end_pipeline_conceptual(tmp_path: Path) -> None:
    """End-to-end conceptual integration test for converse pipeline:
    Audio -> STT -> Text -> Memory Retrieval -> Cognition -> LLM Response."""
    db_file = str(tmp_path / "test_pipeline.db")

    # 1. Setup Configuration & AURA System
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "groq")
    cfg.set("audio.input_device", "C920")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    # 2. Add sample Fact to Memory (Color favorito: azul)
    mem_mod = aura.container.resolve(MemoryModule)
    mem_mod.semantic.add_fact(
        Fact(
            subject="usuario",
            predicate="color_favorito",
            object_val="azul",
            confidence=1.0,
            source="user",
        )
    )

    # 3. Simulate Microphone Recording (16kHz mono PCM WAV)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(np.ones(16000, dtype=np.int16).tobytes())
    sample_wav_bytes = buf.getvalue()

    recorder = MicrophoneRecorder(device="C920")
    with patch.object(recorder, "record_until_silence", return_value=sample_wav_bytes):
        captured_audio = recorder.record_until_silence(max_duration_sec=10.0, silence_sec=1.2)
        assert len(captured_audio) > 44

    # 4. Simulate STT Transcription (FasterWhisper)
    mock_stt_result = MagicMock()
    mock_stt_result.text = "¿Cuál es mi color favorito?"
    mock_stt_result.confidence = 0.95

    stt = FasterWhisperSTTProvider(model_size_or_path="base", device="cpu")
    with patch.object(stt, "transcribe", return_value=mock_stt_result):
        transcribed = stt.transcribe(captured_audio, language="es")
        user_text = transcribed.text.strip()
        assert user_text == "¿Cuál es mi color favorito?"

    # 5. Process through Cognition & LLM
    cog = aura.container.resolve(CognitionModule)

    mock_llm_resp = LLMResponse(
        content="Tu color favorito es el azul.",
        tokens_used=18,
    )
    with patch.object(cog.llm_provider, "generate_response", return_value=mock_llm_resp):
        reasoning = cog.process_cognitive_cycle(user_text)
        aura_response = reasoning.summary

    assert "azul" in aura_response.lower()

    # 6. Verify Memory Retrieval was relevant and selective
    retrieval_res = mem_mod.retrieval.query(user_text)
    assert len(retrieval_res.facts) == 1
    assert retrieval_res.facts[0].predicate == "color_favorito"
    assert retrieval_res.facts[0].object_val == "azul"

    # 7. Verify irrelevant query does NOT inject facts
    irrelevant_retrieval = mem_mod.retrieval.query("Que de ahí se te oyen.")
    assert len(irrelevant_retrieval.facts) == 0

    aura.shutdown(wait=True)
