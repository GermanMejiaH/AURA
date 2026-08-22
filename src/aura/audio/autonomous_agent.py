from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..cognition.intent import ControlIntentDetector
from .edge_tts_provider import EdgeTTSProvider
from .faster_whisper_stt import FasterWhisperSTTProvider
from .microphone import MicrophoneRecorder

if TYPE_CHECKING:
    from ..cognition.module import CognitionModule
    from ..cognition.provider import LLMProvider
    from ..events import EventBus


class AutonomousVoiceAgent:
    """Continuous Autonomous Voice Agent for AURA.

    Features:
    1. Continuous VAD & Audio Mutex: Mutes mic input while AURA speaks.
    2. Deterministic Pre-LLM Control: Intercepts EXIT/CANCEL commands before calling LLM.
    3. Memory-Augmented Decision Making: Uses CognitionModule/MemoryRetrievalEngine for facts.
    4. Robust Reminders: Validates text fields before scheduling background notifications.
    """

    SYSTEM_DECISION_PROMPT = (
        "Eres AURA, una IA con razonamiento autónomo, memoria y gestión del tiempo.\n"
        "Analiza la voz del usuario y la hora actual dada para tomar la decisión ideal.\n\n"
        "Debes responder ÚNICAMENTE con un JSON válido en este formato exacto:\n"
        "{\n"
        '  "action": "IGNORE" | "RESPOND" | "EXECUTE",\n'
        '  "response": "Respuesta directa, amable y fluida en español",\n'
        '  "reasoning": "razón breve",\n'
        '  "reminder": {"text": "descripción", "delay_seconds": 60}\n'
        "}\n\n"
        "REGLAS:\n"
        "1. SI EL USUARIO PIDE UN RECORDATORIO (ej. 'recuérdame...', 'agrega un recordatorio'):\n"
        "   - Pon action: 'EXECUTE'.\n"
        "   - En 'response', confirma amablemente la hora estimada en que se lo recordarás.\n"
        "   - Incluye el objeto 'reminder' con 'text' y 'delay_seconds'.\n"
        "2. SI ES UNA PREGUNTA O SALUDO: usa action: 'RESPOND' y da la respuesta completa.\n"
        "3. SI ES RUIDO O HABLA AJENA: usa action: 'IGNORE' y response: ''.\n"
    )

    def __init__(
        self,
        llm_provider: LLMProvider,
        stt_provider: FasterWhisperSTTProvider | None = None,
        tts_provider: EdgeTTSProvider | None = None,
        event_bus: EventBus | None = None,
        scheduler: Any | None = None,
        cognition_module: CognitionModule | None = None,
        on_decision: Callable[[dict[str, Any]], None] | None = None,
        input_device: int | str | None = None,
    ) -> None:
        import os

        self.llm = llm_provider
        self.stt = stt_provider or FasterWhisperSTTProvider(model_size_or_path="base", device="cpu")
        self.tts = tts_provider or EdgeTTSProvider(voice="es-aura")
        self.event_bus = event_bus
        self.scheduler = scheduler
        self.cognition = cognition_module
        self.on_decision = on_decision

        target_dev = input_device
        if target_dev is None or target_dev == "":
            target_dev = os.environ.get("AURA_AUDIO_INPUT_DEVICE", "C920")

        self.recorder = MicrophoneRecorder(device=target_dev)
        self._running = False
        self._is_speaking = False
        self._speech_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Starts the continuous autonomous voice monitoring loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stops the continuous listening loop."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def is_active(self) -> bool:
        return self._running

    def interrupt_speaking(self) -> None:
        """Immediately interrupts TTS playback if user speaks while AURA is talking."""
        with self._speech_lock:
            if self._is_speaking:
                self._is_speaking = False
                self.tts.stop()
                print("\n  🤐 [AURA detectó tu voz y guardó silencio]")

    def _loop(self) -> None:
        """Continuous background loop: Listen VAD -> Transcribe -> Decide -> Act/Speak/Ignore."""
        self._running = True
        print("\n" + "=" * 65)
        print("  MODO AUTONOMO CONTINUO ACTIVO — AURA TE ESCUCHA Y DECIDE")
        print("  Habla libremente. AURA decidira si responder, actuar o guardar silencio.")
        print(f"  [AUTO] Dispositivo de entrada resuelto: '{self.recorder.device}'")
        print("  [AUTO] Threshold VAD: 120.0 (Sincronizado con CONVERSE)")
        print("=" * 65 + "\n")

        greetings = "Modo autónomo activado. Estoy escuchando."
        print(f"[AURA]: {greetings}")
        self._speak(greetings)

        while self._running:
            try:
                # Audio Mutex Check: If AURA is currently speaking, do not capture microphone
                with self._speech_lock:
                    currently_speaking = self._is_speaking

                if currently_speaking:
                    time.sleep(0.1)
                    continue

                print("  [AUTO] Esperando voz...")
                # 1. Listen until user stops speaking
                audio_bytes = self.recorder.record_until_silence(
                    max_duration_sec=15.0,
                    silence_sec=1.2,
                    energy_threshold=120.0,
                )

                # Audio Mutex Guard: Discard audio captured if TTS playback started during capture
                with self._speech_lock:
                    currently_speaking = self._is_speaking

                if currently_speaking or not audio_bytes or len(audio_bytes) < 4000:
                    time.sleep(0.05)
                    continue

                from ..telemetry import TelemetryManager

                telemetry = TelemetryManager.get_instance()
                t_turn_start = time.perf_counter()

                print(f"  [AUTO] Captura retorno {len(audio_bytes)} bytes de audio")

                # 2. Transcribe speech
                t_stt_0 = time.perf_counter()
                stt_res = self.stt.transcribe(audio_bytes, language="es")
                t_stt_elapsed = (time.perf_counter() - t_stt_0) * 1000
                user_text = stt_res.text.strip()

                if not user_text:
                    continue

                telemetry.increment("speech_events_detected")
                telemetry.record_latency("time_stt_ms", t_stt_elapsed)

                # 3. Deterministic Pre-LLM Control Intent Check for EXIT
                if ControlIntentDetector.is_exit(user_text):
                    telemetry.increment("fastpath_exit_commands")
                    telemetry.record_interaction(user_text, "EXIT")
                    farewell = "Desactivando modo autónomo continuo. Hasta luego."
                    print(f"\n[AURA]: {farewell}")
                    self._speak(farewell)
                    telemetry.record_latency(
                        "time_turn_ms", (time.perf_counter() - t_turn_start) * 1000
                    )
                    break

                # 4. Interruption check if barge-in triggered
                self.interrupt_speaking()

                print(f"\n[Voz Detectada]: '{user_text}'")

                # --- FAST PATH 1: GREETINGS (0 LLM Calls) ---
                if ControlIntentDetector.is_greeting(user_text):
                    telemetry.increment("fastpath_greetings")
                    telemetry.record_interaction(user_text, "FASTPATH_GREETING")
                    greeting_resp = ControlIntentDetector.get_greeting_response()
                    print("  ⚡ [FAST-PATH]: Saludo detectado (0 llamadas LLM)")
                    print(f"[AURA]: {greeting_resp}")
                    self._speak(greeting_resp)
                    telemetry.record_latency(
                        "time_turn_ms", (time.perf_counter() - t_turn_start) * 1000
                    )
                    continue

                # --- FAST PATH 2: DIRECT MEMORY RECALL (0 LLM Calls) ---
                if ControlIntentDetector.is_direct_memory_query(user_text):
                    memory_answered = False
                    if self.cognition is not None and getattr(self.cognition, "_container", None):
                        from ..memory import MemoryModule

                        container = self.cognition._container
                        if container and container.has(MemoryModule):
                            mem_mod = container.resolve(MemoryModule)
                            res_retrieval = mem_mod.retrieval.query(user_text)

                            top_fact = res_retrieval.facts[0] if res_retrieval.facts else None
                            top_pref = (
                                res_retrieval.preferences[0] if res_retrieval.preferences else None
                            )

                            if top_fact and top_fact.confidence >= 0.85:
                                ans = f"Tu {top_fact.predicate} es {top_fact.object_val}."
                                print(
                                    "  ⚡ [FAST-PATH]: Hecho recuperado de memoria "
                                    f"(0 llamadas LLM, conf={top_fact.confidence:.2f})"
                                )
                                print(f"[AURA]: {ans}")
                                self._speak(ans)
                                memory_answered = True
                            elif top_pref:
                                ans = f"Tu preferencia para {top_pref.key} es {top_pref.value}."
                                print(
                                    "  ⚡ [FAST-PATH]: Preferencia recuperada de memoria "
                                    "(0 llamadas LLM)"
                                )
                                print(f"[AURA]: {ans}")
                                self._speak(ans)
                                memory_answered = True

                    if memory_answered:
                        telemetry.increment("fastpath_memory_queries")
                        telemetry.record_interaction(user_text, "FASTPATH_MEMORY")
                        telemetry.record_latency(
                            "time_turn_ms", (time.perf_counter() - t_turn_start) * 1000
                        )
                        continue

                # 5. Cognitive decision & response (Single-pass when cognition available)
                if self.cognition is not None:
                    # SINGLE-PASS PATH: Directly run process_cognitive_cycle (1 LLM call)
                    cognition_result = self.cognition.process_cognitive_cycle(user_text)
                    response_text = cognition_result.summary.strip()
                    action = (
                        "RESPOND"
                        if response_text and not response_text.startswith("[IGNORE]")
                        else "IGNORE"
                    )
                    decision = {
                        "action": action,
                        "response": response_text,
                        "reasoning": "Single-pass cognitive cycle",
                    }

                    if self.on_decision is not None:
                        self.on_decision(decision)

                    telemetry.record_interaction(user_text, action)
                    print(f"  🤔 Decisión Cognitiva -> [{action}] (single-pass)")

                    if action == "RESPOND" and response_text:
                        print(f"[AURA]: {response_text}")
                        self._speak(response_text)
                    elif action == "IGNORE":
                        print("  🤫 [AURA decidió guardar silencio]")
                else:
                    # LEGACY FALLBACK PATH: Standalone mode without CognitionModule
                    decision = self._make_decision(user_text)

                    if self.on_decision is not None:
                        self.on_decision(decision)

                    action = decision.get("action", "IGNORE")
                    response_text = decision.get("response", "").strip()
                    reasoning = decision.get("reasoning", "")

                    telemetry.record_interaction(user_text, action)
                    print(f"  🤔 Decisión Cognitiva (Fallback) -> [{action}] ({reasoning})")

                    if action in ("RESPOND", "EXECUTE"):
                        if response_text:
                            print(f"[AURA]: {response_text}")
                            self._speak(response_text)

                        reminder = decision.get("reminder")
                        if isinstance(reminder, dict):
                            self._schedule_reminder(reminder)

                    elif action == "IGNORE":
                        print("  🤫 [AURA decidió guardar silencio]")

                telemetry.record_latency(
                    "time_turn_ms", (time.perf_counter() - t_turn_start) * 1000
                )

            except Exception as exc:
                time.sleep(0.3)
                _ = exc

    def _schedule_reminder(self, reminder: dict[str, Any]) -> None:
        """Schedules a gentle reminder with robust text field validation."""
        if not isinstance(reminder, dict):
            return

        delay = float(reminder.get("delay_seconds", 60))
        if delay < 1.0:
            delay = 1.0

        # Robust text extraction across alternate keys: "text", "description", "message", "action"
        text = ""
        for field_key in ("text", "description", "message", "action"):
            val = reminder.get(field_key)
            if val and isinstance(val, str) and val.strip():
                text = val.strip()
                break

        if not text:
            # Reject empty reminder
            print("  [WARN] Recordatorio rechazado: texto de recordatorio vacio.")
            return

        reminder_text = text  # capture non-empty text in closure

        def _notify() -> None:
            msg = f"Hola, te recuerdo suavemente: {reminder_text}."
            print(f"\n  ⏰ [RECORDATORIO AURA]: {msg}")
            self._speak(msg)

        if self.scheduler is not None and hasattr(self.scheduler, "schedule_once"):
            self.scheduler.schedule_once(
                name=f"Reminder_{reminder_text[:20]}",
                func=_notify,
                when=delay,
            )
        else:
            timer = threading.Timer(delay, _notify)
            timer.daemon = True
            timer.start()

    def _make_decision(self, text: str) -> dict[str, Any]:
        """Calls LLM to decide whether to IGNORE, RESPOND, or EXECUTE."""
        import json
        import re
        from datetime import datetime

        temporal_keywords = (
            "hora",
            "fecha",
            "hoy",
            "mañana",
            "ayer",
            "calendario",
            "agenda",
            "recordatorio",
            "cuándo",
            "cuando",
        )
        norm_text = text.lower()
        has_temporal = any(re.search(rf"\b{re.escape(k)}\b", norm_text) for k in temporal_keywords)
        if has_temporal:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            prompt = (
                f"Fecha y hora actual del sistema: {now_str}\nEntrada de voz del usuario: '{text}'"
            )
        else:
            prompt = f"Entrada de voz del usuario: '{text}'"

        res = self.llm.generate_response(
            prompt=prompt,
            system_instruction=self.SYSTEM_DECISION_PROMPT,
        )

        raw = res.content.strip().removeprefix("```json").removesuffix("```").strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "action" in parsed:
                return parsed
        except Exception:
            pass

        # Fallback if json parsing fails: respond nicely
        return {
            "action": "RESPOND",
            "response": res.content,
            "reasoning": "Respuesta directa del modelo",
        }

    def _speak(self, text: str) -> None:
        """Speaks text using TTS with thread-safe lock and post-speech guard."""
        with self._speech_lock:
            self._is_speaking = True
        try:
            self.tts.speak(text)
        finally:
            # 300ms post-synthesis guard window for acoustic room echo decay
            time.sleep(0.3)
            with self._speech_lock:
                self._is_speaking = False
