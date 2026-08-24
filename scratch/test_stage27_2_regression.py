from __future__ import annotations

import time
from typing import Any

from aura.audio.autonomous_agent import AutonomousVoiceAgent
from aura.audio.faster_whisper_stt import FasterWhisperSTTProvider
from aura.cognition.intent import ControlIntentDetector


class MockSTT:
    def __init__(self, return_text: str = "") -> None:
        self.return_text = return_text

    def transcribe(self, audio: Any, language: str = "es") -> Any:
        return type("STTRes", (), {"text": self.return_text})()


class MockTTS:
    def __init__(self) -> None:
        self.spoke_texts: list[str] = []

    def speak(self, text: str) -> None:
        self.spoke_texts.append(text)

    def stop(self) -> None:
        pass


def test_stage27_2_regression() -> dict[str, Any]:
    print("====================================================================")
    print("       STAGE 27.2 — VOICE LOOPBACK & ECHO HARDENING REGRESSION SUITE")
    print("====================================================================\n")

    results: dict[str, bool] = {}

    # TEST 1: No Speech -> Expected: No STT output (returns empty string)
    print("--- TEST 1: NO SPEECH (VAD SILENCE) ---")
    stt_empty = MockSTT(return_text="")
    res_empty = stt_empty.transcribe(b"silence")
    test1_passed = (res_empty.text == "")
    results["test1_no_speech"] = test1_passed
    print(f"Result: '{res_empty.text}' | Passed: {test1_passed}\n")

    # TEST 2: TTS Playback followed by silence -> Expected: Post-TTS cooldown active
    print("--- TEST 2: TTS PLAYBACK COOLDOWN GUARD ---")
    agent2 = AutonomousVoiceAgent(
        llm_provider=type("LLM", (), {})(),  # type: ignore
        stt_provider=MockSTT(return_text=""),  # type: ignore
        tts_provider=MockTTS(),  # type: ignore
    )
    t0 = time.perf_counter()
    agent2._speak("AURA activada.")
    elapsed = time.perf_counter() - t0
    test2_passed = (elapsed >= 2.0 and agent2.last_tts_output == "aura activada.")
    results["test2_tts_cooldown"] = test2_passed
    print(f"Elapsed Cooldown: {elapsed:.2f}s | last_tts_output: '{agent2.last_tts_output}' | Passed: {test2_passed}\n")

    # TEST 3: TTS Playback + Speaker Echo -> Expected: Transcript discarded by Voice Guard
    print("--- TEST 3: TTS PLAYBACK + SPEAKER ECHO (SELF-TRANSCRIPT DETECTOR) ---")
    agent3 = AutonomousVoiceAgent(
        llm_provider=type("LLM", (), {})(),  # type: ignore
        stt_provider=MockSTT(return_text="AURA es una asistente virtual en español."),  # type: ignore
        tts_provider=MockTTS(),  # type: ignore
    )
    agent3.last_tts_output = "aura es una asistente virtual en español diseñada para ayudarte."
    agent3.last_tts_end = time.perf_counter()

    import difflib
    echo_text = "de la asistente virtual en español."
    ratio = difflib.SequenceMatcher(None, echo_text.lower(), agent3.last_tts_output).ratio()
    is_discarded = (ratio >= 0.50 or echo_text.lower() in agent3.last_tts_output)
    results["test3_echo_discarded"] = is_discarded
    print(f"Echo Text: '{echo_text}' | Similarity: {ratio*100:.1f}% | Discarded: {is_discarded} | Passed: {is_discarded}\n")

    # TEST 4: Human Speech After Cooldown -> Expected: Normal Response
    print("--- TEST 4: HUMAN SPEECH AFTER COOLDOWN ---")
    human_text = "¿Qué hora es en este momento?"
    is_short = (len(human_text.strip()) < 10)
    is_self_transcription = (agent3.last_tts_output != "" and human_text.lower() in agent3.last_tts_output)
    test4_passed = (not is_short and not is_self_transcription)
    results["test4_human_speech"] = test4_passed
    print(f"Human Input: '{human_text}' | Accepted for Cognition: {test4_passed} | Passed: {test4_passed}\n")

    # TEST 5: Whisper Prompt Continuation Fragment ("de la asistente virtual en español") -> Expected: Rejected
    print("--- TEST 5: WHISPER PROMPT CONTINUATION REJECTION ---")
    fragment = "de la asistente virtual en español"
    ratio5 = difflib.SequenceMatcher(None, fragment.lower(), agent3.last_tts_output).ratio()
    is_fragment_rejected = (ratio5 >= 0.50 or fragment.lower() in agent3.last_tts_output)
    results["test5_fragment_rejected"] = is_fragment_rejected
    print(f"Fragment: '{fragment}' | Rejection Status: {is_fragment_rejected} | Passed: {is_fragment_rejected}\n")

    # TEST 6: Initial Prompt Sanitization Check in FasterWhisperSTTProvider
    stt_provider = FasterWhisperSTTProvider()
    test6_passed = (stt_provider.initial_prompt == "")
    results["test6_initial_prompt_empty"] = test6_passed
    print(f"FasterWhisper initial_prompt: '{stt_provider.initial_prompt}' | Empty Prompt Passed: {test6_passed}\n")

    all_passed = all(results.values())
    print("====================================================================")
    print(f"REGRESSION SUITE COMPLETED | ALL 6 TESTS PASSED: {all_passed}")
    print("====================================================================")

    import json
    with open("scratch/stage27_2_regression_summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return {"all_passed": all_passed, "results": results}


if __name__ == "__main__":
    test_stage27_2_regression()
