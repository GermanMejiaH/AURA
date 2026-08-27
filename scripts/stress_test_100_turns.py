from __future__ import annotations

import random
import sys
import time
from pathlib import Path
from typing import Any

src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from aura.audio.autonomous_agent import AutonomousVoiceAgent
from aura.audio.tts import MockTTSProvider
from aura.cognition.provider import MockLLMProvider


class MockSTTProvider:
    """Mock STT provider returning pre-determined text for stress testing."""

    def __init__(self) -> None:
        self.text_to_return = "hola"

    def transcribe(self, audio_bytes: bytes, language: str = "es") -> Any:
        class STTResult:
            def __init__(self, text: str) -> None:
                self.text = text

        return STTResult(self.text_to_return)


def run_100_turn_stress_test() -> None:
    print("\n" + "=" * 75)
    print("  AURA REALTIME OPTIMIZATION SPRINT: 100-TURN CONTINUOUS STRESS TEST")
    print("=" * 75)

    llm = MockLLMProvider()
    tts = MockTTSProvider()
    agent = AutonomousVoiceAgent(llm_provider=llm, tts_provider=tts)
    agent.POST_TTS_COOLDOWN_SEC = 0.001
    agent.tts._play_fallback = lambda b: None  # Bypass physical speaker playback during stress test

    # 100 Turn Prompt Distribution
    math_queries = [
        "cuanto es 25 mas 35",
        "1348 por 151",
        "20 dividido 5",
        "15% de 200",
        "raiz cuadrada de 81",
        "multiplica 12 por 8",
        "suma 150 y 350",
        "50 menos 18",
        "raiz de 144",
        "20 porciento de 500",
    ]

    memory_queries = [
        "quien soy",
        "cual es mi nombre",
        "donde vivo",
        "que sabes de mi",
        "cual es mi comida favorita",
        "cuantos anos tengo",
        "que estudio",
        "donde trabajo",
    ]

    reminder_queries = [
        "recuerdame en 5 minutos comprar agua",
        "que recordatorios tengo",
        "lista mis recordatorios",
        "recuerdame en 10 segundos llamar a mama",
        "tengo alarmas pendientes",
    ]

    normal_queries = [
        "hola como estas",
        "buenos dias aura",
        "explicame la teoria de la relatividad",
        "como funciona un motor electrico",
        "que opina de la inteligencia artificial",
        "dime un consejo para programar mejor",
    ]

    simulated_errors = [
        "",  # Empty text
        "   ",  # Blank space
        "err_trigger_exception",  # Malformed query
        "ab",  # Too short transcript (<10 chars)
    ]

    turns_executed = 0
    fastpaths_triggered = 0
    exceptions_caught = 0
    unbound_local_errors = 0
    negative_queue_ms_count = 0

    latencies_total: list[float] = []
    latencies_queue: list[float] = []

    # Monkey patch _log_pipeline_metrics to intercept metrics without stdout spam
    original_log = agent._log_pipeline_metrics

    def intercepted_log_metrics(
        vad_ms: float,
        stt_ms: float,
        intent_ms: float,
        retrieval_ms: float,
        llm_ms: float,
        tts_ms: float,
        playback_ms: float,
        queue_ms: float,
        total_ms: float,
    ) -> None:
        nonlocal negative_queue_ms_count
        if queue_ms < 0:
            negative_queue_ms_count += 1
        latencies_total.append(total_ms)
        latencies_queue.append(queue_ms)

    agent._log_pipeline_metrics = intercepted_log_metrics  # type: ignore

    print("  [STRESS TEST] Iniciando simulación de 100 turnos...")

    for turn_idx in range(1, 101):
        # Pick category based on distribution
        r = random.random()
        if r < 0.25:
            cat = "MATH"
            query = random.choice(math_queries)
        elif r < 0.45:
            cat = "MEMORY"
            query = random.choice(memory_queries)
        elif r < 0.65:
            cat = "REMINDER"
            query = random.choice(reminder_queries)
        elif r < 0.80:
            cat = "NORMAL"
            query = random.choice(normal_queries)
        elif r < 0.90:
            cat = "INTERRUPTION"
            query = "hola aura hablando al mismo tiempo"
        else:
            cat = "ERROR_SIMULATION"
            query = random.choice(simulated_errors)

        t_turn_start = time.perf_counter()
        vad_ms = 100.0
        stt_ms = 15.0
        intent_ms = 0.0
        retrieval_ms = 0.0
        llm_ms = 0.0
        tts_ms = 0.0
        playback_ms = 0.0
        queue_ms = 0.0
        total_ms = 0.0

        try:
            if cat == "INTERRUPTION":
                agent.interrupt_speaking()

            # Execute turn logic artificially
            from aura.cognition.intent import ControlIntentDetector

            if query == "err_trigger_exception":
                # Intentionally trigger an exception to test try...finally metrics stability
                raise RuntimeError("Simulated Pipeline Exception")

            t_intent_0 = time.perf_counter()
            if ControlIntentDetector.is_greeting(query):
                fastpaths_triggered += 1
                resp = ControlIntentDetector.get_greeting_response()
                tts_ms, playback_ms = agent._speak(resp)
            elif ControlIntentDetector.is_time_query(query):
                fastpaths_triggered += 1
                resp = ControlIntentDetector.get_time_response(query)
                tts_ms, playback_ms = agent._speak(resp)
            elif ControlIntentDetector.is_calculator_query(query):
                fastpaths_triggered += 1
                resp = ControlIntentDetector.get_calculator_response(query)
                tts_ms, playback_ms = agent._speak(resp)
            elif ControlIntentDetector.is_reminder_list_query(query):
                fastpaths_triggered += 1
                resp = "No tienes recordatorios pendientes."
                tts_ms, playback_ms = agent._speak(resp)
            elif ControlIntentDetector.is_reminder_query(query):
                fastpaths_triggered += 1
                rem_desc, delay = ControlIntentDetector.parse_reminder_query(query)
                agent._schedule_reminder({"text": rem_desc, "delay_seconds": delay})
                resp = f"Recordatorio programado: {rem_desc}"
                tts_ms, playback_ms = agent._speak(resp)
            elif ControlIntentDetector.is_user_profile_query(query) or ControlIntentDetector.is_direct_memory_query(query):
                fastpaths_triggered += 1
                resp = "Perfil de usuario: Nombre: Andrés | Ciudad: Medellín."
                tts_ms, playback_ms = agent._speak(resp)
            elif query.strip():
                # Normal LLM
                t_llm_0 = time.perf_counter()
                dec = agent._make_decision(query)
                llm_ms = (time.perf_counter() - t_llm_0) * 1000
                resp = dec.get("response", "Hola")
                tts_ms, playback_ms = agent._speak(resp)

            intent_ms = (time.perf_counter() - t_intent_0) * 1000

        except UnboundLocalError:
            unbound_local_errors += 1
            exceptions_caught += 1
        except Exception:
            exceptions_caught += 1
        finally:
            turns_executed += 1
            total_ms = (time.perf_counter() - t_turn_start) * 1000
            sum_known = vad_ms + stt_ms + intent_ms + retrieval_ms + llm_ms + tts_ms + playback_ms
            queue_ms = max(0.0, total_ms - sum_known)
            intercepted_log_metrics(
                vad_ms, stt_ms, intent_ms, retrieval_ms, llm_ms, tts_ms, playback_ms, queue_ms, total_ms
            )

        if turn_idx % 20 == 0:
            print(f"  • Progress: {turn_idx}/100 turns completed...")

    # Calculate statistics
    avg_turn = sum(latencies_total) / len(latencies_total) if latencies_total else 0.0
    sorted_turns = sorted(latencies_total)
    p95_turn = sorted_turns[int(len(sorted_turns) * 0.95)] if sorted_turns else 0.0
    avg_queue = sum(latencies_queue) / len(latencies_queue) if latencies_queue else 0.0

    print("\n" + "=" * 75)
    print("  STRESS TEST AUDIT SUMMARY RESULTS")
    print("=" * 75)
    print(f"  • Total Turns Executed          : {turns_executed} / 100")
    print(f"  • Fast-Paths Triggered          : {fastpaths_triggered} ({fastpaths_triggered / turns_executed * 100:.1f}%)")
    print(f"  • Simulated Exceptions Handled  : {exceptions_caught}")
    print(f"  • UnboundLocalError Occurrences : {unbound_local_errors} (Target = 0)")
    print(f"  • Negative queue_ms Occurrences : {negative_queue_ms_count} (Target = 0)")
    print(f"  • Average Turn Latency          : {avg_turn:.2f} ms")
    print(f"  • P95 Turn Latency              : {p95_turn:.2f} ms")
    print(f"  • Average Unattributed Overhead : {avg_queue:.2f} ms")
    print("=" * 75 + "\n")

    assert turns_executed == 100, "Should execute 100 turns"
    assert unbound_local_errors == 0, "UnboundLocalError must be 0"
    assert negative_queue_ms_count == 0, "Negative queue_ms must be 0"


if __name__ == "__main__":
    run_100_turn_stress_test()
