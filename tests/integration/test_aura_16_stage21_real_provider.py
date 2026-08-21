"""Stage 21 — Real Gemini Provider Smoke Test.

Executes a real end-to-end cognitive provider turn using Google Gemini API
(GeminiLLMProvider) when GEMINI_API_KEY is present in the environment or .env file.
If credentials are absent, the test skips cleanly without breaking CI/tests.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from aura.cognition import CognitiveMode, GeminiLLMProvider
from aura.cognition.scheduling import (
    ConversationalRuntime,
    RuntimeOperationState,
)
from aura.logging import get_logger

logger = get_logger("RealGeminiSmokeTest")


def _get_real_gemini_api_key() -> str | None:
    """Helper to detect real GEMINI_API_KEY from environment or .env file."""
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "GEMINI_API_KEY":
                    val = v.strip().strip("'\"")
                    if val and not val.startswith("fake_") and val != "tu-api-key":
                        return val

    key = os.environ.get("GEMINI_API_KEY", "")
    if key and not key.startswith("fake_") and key != "tu-api-key":
        return key
    return None


def test_real_gemini_provider_smoke_test() -> None:
    """Smoke test running real Gemini cognitive interpretation + Stage 16 closed-loop execution."""
    api_key = _get_real_gemini_api_key()
    if not api_key:
        pytest.skip(
            "GEMINI_API_KEY not configured in environment or .env file. Skipping real Gemini API"
            " smoke test."
        )

    provider = GeminiLLMProvider(api_key=api_key, model_name="gemini-2.5-flash")
    runtime = ConversationalRuntime(llm_provider=provider)

    try:
        start_t = time.perf_counter()
        res = runtime.process_turn(
            conversation_id="conv_real_gemini_smoke",
            user_input="¿Qué fecha y hora es hoy?",
        )
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)

        # Audit output logging (secrets strictly excluded)
        logger.info(
            f"Real Gemini Smoke Test Completed in {elapsed_ms}ms | Model: gemini-2.5-flash | "
            f"Action: {res.action_id} | OperationState: {res.operation.state.value} | "
            f"Trace: operation_id={res.operation_id}, correlation_id={res.correlation_id}"
        )

        assert res.cognitive_interpretation is not None
        assert res.cognitive_interpretation.mode in (
            CognitiveMode.TOOL_PROPOSAL,
            CognitiveMode.DIRECT_RESPONSE,
        )
        assert res.operation.state == RuntimeOperationState.COMPLETED
        assert res.success is True
        assert len(res.natural_response) > 0
    finally:
        runtime.close()
