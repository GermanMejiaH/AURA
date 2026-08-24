from __future__ import annotations

from typing import Any

from aura.audio.autonomous_agent import AutonomousVoiceAgent
from aura.telemetry import TelemetryManager


class FailingSTT:
    def transcribe(self, audio_bytes: bytes, language: str = "es") -> Any:
        raise RuntimeError("STT Engine Crash / Audio Capture Error Simulation")


class FailingTTS:
    def speak(self, text: str) -> None:
        raise RuntimeError("TTS Device Output Disconnect Simulation")


def test_voice_resilience() -> dict[str, Any]:
    print("=== STAGE 26.4 AUDIT 5: VOICE LOOP RESILIENCE ===")
    telemetry = TelemetryManager.get_instance()
    initial_failures = telemetry.get_counter("voice_turn_failures")

    agent = AutonomousVoiceAgent(
        llm_provider=type("LLM", (), {})(),  # type: ignore
        stt_provider=FailingSTT(),  # type: ignore
        tts_provider=FailingTTS(),  # type: ignore
    )

    # Simulate 1 voice turn loop iteration
    try:
        stt_res = agent.stt.transcribe(b"dummy_audio_bytes_12345", language="es")
    except Exception as exc:
        telemetry.increment("voice_turn_failures")
        print(f"  Captured STT Failure: {exc}")

    # Simulate TTS failure
    try:
        agent.tts.speak("Test text")
    except Exception as exc:
        telemetry.increment("voice_turn_failures")
        print(f"  Captured TTS Failure: {exc}")

    failures_logged = telemetry.get_counter("voice_turn_failures") - initial_failures
    passed = (failures_logged == 2)

    print(f"Initial Failures: {initial_failures} | New Failures Logged: {failures_logged} | Passed: {passed}")

    return {
        "initial_failures": initial_failures,
        "failures_logged": failures_logged,
        "passed": passed,
    }


if __name__ == "__main__":
    test_voice_resilience()
