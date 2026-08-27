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

    POST_TTS_COOLDOWN_SEC: float = 2.0

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
        self.stt = stt_provider or FasterWhisperSTTProvider(
            model_size_or_path="small", device="cpu"
        )
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

        self.last_tts_output: str = ""
        self.last_tts_end: float = 0.0

        self._awaiting_exit_confirmation: bool = False
        self._exit_confirmation_time: float = 0.0

    @staticmethod
    def is_low_quality_transcript(text: str) -> bool:
        """Evaluates whether transcript is low-quality nonsense or repetitive."""
        clean = text.lower().strip()
        words = clean.split()
        if not words:
            return True

        # Check for immediate consecutive repeated words (e.g. "y si no no", "no no no")
        for i in range(len(words) - 1):
            if words[i] == words[i + 1] and len(words[i]) <= 3:
                return True

        # Blacklist of common low-confidence Spanish n-gram hallucinations
        nonsense_patterns = (
            "y si no no",
            "de que pueda ser bajo",
            "ayer es un chico",
            "y si no",
            "no no",
            "eh eh",
            "mmm mmm",
            "subtítulos",
            "subtitulos",
            "transcripción",
            "transcripcion",
            "suscríbete",
            "suscribete",
            "gracias por ver",
            "comunidad de youtube",
        )
        if any(pat in clean for pat in nonsense_patterns):
            return True

        # Check lexical diversity (unique words / total words) for longer transcripts
        if len(words) >= 4:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.5:
                return True

        # Stop words filter for meaningful tokens
        stop_words = {
            "y",
            "o",
            "de",
            "del",
            "la",
            "el",
            "un",
            "una",
            "los",
            "las",
            "en",
            "por",
            "para",
            "con",
            "sin",
            "no",
            "si",
            "sí",
            "que",
            "es",
            "ser",
            "se",
        }
        meaningful_tokens = [w for w in words if w not in stop_words and len(w) >= 3]

        if len(meaningful_tokens) < 1:
            return True

        return False

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

    def _log_pipeline_metrics(
        self,
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
        print(
            f"\n  📊 [PIPELINE]\n"
            f"  vad_ms={vad_ms:.1f}\n"
            f"  stt_ms={stt_ms:.1f}\n"
            f"  intent_ms={intent_ms:.1f}\n"
            f"  retrieval_ms={retrieval_ms:.1f}\n"
            f"  llm_ms={llm_ms:.1f}\n"
            f"  tts_ms={tts_ms:.1f}\n"
            f"  playback_ms={playback_ms:.1f}\n"
            f"  queue_ms={queue_ms:.1f}\n"
            f"  total_ms={total_ms:.1f}"
        )

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
            t_vad_ms = 0.0
            t_stt_ms = 0.0
            t_intent_ms = 0.0
            t_retrieval_ms = 0.0
            t_llm_ms = 0.0
            t_tts_ms = 0.0
            t_playback_ms = 0.0
            t_queue_ms = 0.0
            t_total_ms = 0.0
            t_turn_start = 0.0

            # Audio Mutex Check: If AURA is currently speaking, do not capture microphone
            with self._speech_lock:
                currently_speaking = self._is_speaking

            if currently_speaking:
                time.sleep(0.1)
                continue

            print("  [AUTO] Esperando voz...")
            t_vad_0 = time.perf_counter()
            audio_bytes = self.recorder.record_until_silence(
                max_duration_sec=15.0,
                silence_sec=0.8,
                energy_threshold=120.0,
            )
            t_vad_ms = (time.perf_counter() - t_vad_0) * 1000

            with self._speech_lock:
                currently_speaking = self._is_speaking

            if currently_speaking or not audio_bytes or len(audio_bytes) < 4000:
                time.sleep(0.05)
                continue

            from ..telemetry import TelemetryManager

            telemetry = TelemetryManager.get_instance()
            t_turn_start = time.perf_counter()

            print(f"  [AUTO] Captura retorno {len(audio_bytes)} bytes de audio")

            t_stt_0 = time.perf_counter()
            stt_res = self.stt.transcribe(audio_bytes, language="es")
            t_stt_ms = (time.perf_counter() - t_stt_0) * 1000
            user_text = stt_res.text.strip()

            if not user_text:
                continue

            try:
                import difflib

                is_exit_cmd = ControlIntentDetector.is_exit(user_text)
                is_greeting_cmd = ControlIntentDetector.is_greeting(user_text)

                if len(user_text.strip()) < 10 and not (
                    is_exit_cmd or is_greeting_cmd or self._awaiting_exit_confirmation
                ):
                    print(f"  🛑 [VOICE GUARD] Transcript rejected (too short: '{user_text}')")
                    continue

                if self.last_tts_output:
                    ratio = difflib.SequenceMatcher(
                        None, user_text.lower(), self.last_tts_output
                    ).ratio()
                    if ratio >= 0.70 or user_text.lower() in self.last_tts_output:
                        print(
                            "  🛑 [VOICE GUARD] Self-transcription detected "
                            f"(similarity={ratio * 100:.1f}%). Discarded."
                        )
                        continue

                time_since_tts = time.perf_counter() - self.last_tts_end
                if time_since_tts < self.POST_TTS_COOLDOWN_SEC:
                    if self.last_tts_output:
                        ratio = difflib.SequenceMatcher(
                            None, user_text.lower(), self.last_tts_output
                        ).ratio()
                        if ratio >= 0.50 or user_text.lower() in self.last_tts_output:
                            print(
                                "  🛑 [VOICE GUARD] Echo window capture discarded "
                                f"({time_since_tts:.2f}s post-TTS)."
                            )
                            continue

                telemetry.increment("speech_events_detected")
                telemetry.record_latency("time_stt_ms", t_stt_ms)

                if self._awaiting_exit_confirmation:
                    elapsed = time.perf_counter() - self._exit_confirmation_time
                    if elapsed > 15.0:
                        self._awaiting_exit_confirmation = False
                        timeout_msg = (
                            "Tiempo de confirmación agotado. Modo autónomo continuo mantenido."
                        )
                        print(f"\n[AURA]: {timeout_msg}")
                        t_tts_ms, t_playback_ms = self._speak(timeout_msg)
                        continue

                    lower_user = user_text.lower().strip()
                    confirm_keywords = (
                        "sí",
                        "si",
                        "afirmativo",
                        "confirmo",
                        "confirmar",
                        "correcto",
                        "de acuerdo",
                        "cerrar",
                        "salir",
                        "salí",
                        "sali",
                        "chao",
                        "bye",
                        "ahora",
                    )

                    if any(kw in lower_user for kw in confirm_keywords):
                        self._awaiting_exit_confirmation = False
                        telemetry.increment("fastpath_exit_commands")
                        telemetry.record_interaction(user_text, "EXIT_CONFIRMED")
                        farewell = "Desactivando modo autónomo continuo. Hasta luego."
                        print(f"\n[AURA]: {farewell}")
                        t_tts_ms, t_playback_ms = self._speak(farewell)
                        break
                    else:
                        self._awaiting_exit_confirmation = False
                        cancel_msg = "Cancelado. Modo autónomo continuo mantenido."
                        print(f"\n[AURA]: {cancel_msg}")
                        t_tts_ms, t_playback_ms = self._speak(cancel_msg)
                        continue

                if (
                    self.is_low_quality_transcript(user_text)
                    and not is_exit_cmd
                    and not is_greeting_cmd
                ):
                    print(
                        f"  🛑 [VOICE GUARD] Transcript rejected by quality filter ('{user_text}')"
                    )
                    continue

                if is_exit_cmd:
                    self._awaiting_exit_confirmation = True
                    print("\n  🛡 EXIT CONFIRMATION MODE")
                    confirm_prompt = "¿Deseas cerrar AURA? Responde sí o no."
                    print(f"[AURA]: {confirm_prompt}")
                    t_tts_ms, t_playback_ms = self._speak(confirm_prompt)
                    self._exit_confirmation_time = time.perf_counter()
                    continue

                self.interrupt_speaking()
                print(f"\n[Voz Detectada]: '{user_text}'")

                t_intent_0 = time.perf_counter()

                # --- FAST PATH 1: GREETINGS (0 LLM Calls) ---
                if ControlIntentDetector.is_greeting(user_text):
                    t_intent_ms = (time.perf_counter() - t_intent_0) * 1000
                    telemetry.increment("fastpath_greetings")
                    telemetry.record_interaction(user_text, "FASTPATH_GREETING")
                    greeting_resp = ControlIntentDetector.get_greeting_response()
                    print("  ⚡ [FAST PATH ACTIVATED] type=greeting (0 llamadas LLM)")
                    print(f"[AURA]: {greeting_resp}")
                    t_tts_ms, t_playback_ms = self._speak(greeting_resp)
                    continue

                # --- FAST PATH 2: TIME & DATE (0 LLM Calls) ---
                if ControlIntentDetector.is_time_query(user_text):
                    t_intent_ms = (time.perf_counter() - t_intent_0) * 1000
                    telemetry.increment("fastpath_time")
                    telemetry.record_interaction(user_text, "FASTPATH_TIME")
                    time_resp = ControlIntentDetector.get_time_response(user_text)
                    print("  ⚡ [FAST PATH ACTIVATED] type=time (0 llamadas LLM)")
                    print(f"[AURA]: {time_resp}")
                    t_tts_ms, t_playback_ms = self._speak(time_resp)
                    continue

                # --- FAST PATH 3: CALCULATOR & MATH (0 LLM Calls) ---
                if ControlIntentDetector.is_calculator_query(user_text):
                    t_intent_ms = (time.perf_counter() - t_intent_0) * 1000
                    telemetry.increment("fastpath_calculator")
                    telemetry.record_interaction(user_text, "FASTPATH_CALCULATOR")
                    calc_resp = ControlIntentDetector.get_calculator_response(user_text)
                    print("  ⚡ [FAST PATH ACTIVATED] type=calculator (0 llamadas LLM)")
                    print(f"[AURA]: {calc_resp}")
                    t_tts_ms, t_playback_ms = self._speak(calc_resp)
                    continue

                # --- FAST PATH 4: REMINDER LISTING (0 LLM Calls) ---
                if ControlIntentDetector.is_reminder_list_query(user_text):
                    t_intent_ms = (time.perf_counter() - t_intent_0) * 1000
                    telemetry.increment("fastpath_reminder_list")
                    telemetry.record_interaction(user_text, "FASTPATH_REMINDER_LIST")
                    if self.scheduler and hasattr(self.scheduler, "list_jobs"):
                        jobs = self.scheduler.list_jobs()
                        if jobs:
                            rem_resp = f"Tienes {len(jobs)} recordatorios activos programados."
                        else:
                            rem_resp = "No tienes ningún recordatorio pendiente en este momento."
                    else:
                        rem_resp = "No tienes recordatorios activos registrados."
                    print("  ⚡ [FAST PATH ACTIVATED] type=reminder_list (0 llamadas LLM)")
                    print(f"[AURA]: {rem_resp}")
                    t_tts_ms, t_playback_ms = self._speak(rem_resp)
                    continue

                # --- FAST PATH 5: REMINDER CREATION (0 LLM Calls) ---
                if ControlIntentDetector.is_reminder_query(user_text):
                    t_intent_ms = (time.perf_counter() - t_intent_0) * 1000
                    telemetry.increment("fastpath_reminder")
                    telemetry.record_interaction(user_text, "FASTPATH_REMINDER")
                    rem_desc, delay_sec = ControlIntentDetector.parse_reminder_query(user_text)
                    self._schedule_reminder({"text": rem_desc, "delay_seconds": delay_sec})
                    delay_int = int(delay_sec)
                    if delay_sec < 60:
                        conf_resp = f"Claro, te recordaré '{rem_desc}' en {delay_int} segundos."
                    else:
                        conf_resp = (
                            f"Claro, te recordaré '{rem_desc}' en {delay_int // 60} minutos."
                        )
                    print("  ⚡ [FAST PATH ACTIVATED] type=reminder (0 llamadas LLM)")
                    print(f"[AURA]: {conf_resp}")
                    t_tts_ms, t_playback_ms = self._speak(conf_resp)
                    continue

                # --- FAST PATH 6: WEATHER (0 LLM Calls) ---
                if ControlIntentDetector.is_weather_query(user_text):
                    t_intent_ms = (time.perf_counter() - t_intent_0) * 1000
                    telemetry.increment("fastpath_weather")
                    telemetry.record_interaction(user_text, "FASTPATH_WEATHER")
                    weather_resp = ControlIntentDetector.get_weather_response(user_text)
                    print("  ⚡ [FAST PATH ACTIVATED] type=weather (0 llamadas LLM)")
                    print(f"[AURA]: {weather_resp}")
                    t_tts_ms, t_playback_ms = self._speak(weather_resp)
                    continue

                # --- FAST PATH 7: USER PROFILE & MEMORY QUERIES (0 LLM Calls) ---
                is_prof_query = ControlIntentDetector.is_user_profile_query(user_text)
                is_mem_query = ControlIntentDetector.is_direct_memory_query(user_text)

                if is_prof_query or is_mem_query:
                    t_intent_ms = (time.perf_counter() - t_intent_0) * 1000
                    memory_answered = False
                    if self.cognition is not None and getattr(self.cognition, "_container", None):
                        from ..memory import MemoryModule

                        container = self.cognition._container
                        if container and container.has(MemoryModule):
                            mem_mod = container.resolve(MemoryModule)
                            t_ret_0 = time.perf_counter()
                            res_retrieval = mem_mod.retrieval.query(user_text)
                            t_retrieval_ms = (time.perf_counter() - t_ret_0) * 1000

                            top_fact = res_retrieval.facts[0] if res_retrieval.facts else None
                            top_pref = (
                                res_retrieval.preferences[0] if res_retrieval.preferences else None
                            )

                            is_open_query = (
                                is_prof_query
                                or mem_mod.retrieval._is_open_recall_query(
                                    user_text, mem_mod.retrieval._get_query_tokens(user_text)
                                )
                            )

                            if is_open_query and (
                                res_retrieval.facts or mem_mod.semantic.all_facts()
                            ):
                                from ..memory.retrieval import normalize_text

                                all_facts = list(mem_mod.semantic.all_facts()) + list(
                                    res_retrieval.facts
                                )
                                fact_dict: dict[str, str] = {}
                                for f in all_facts:
                                    norm_p = normalize_text(f.predicate)
                                    fact_dict[norm_p] = f.object_val

                                profile_parts: list[str] = []
                                name_val = next(
                                    (
                                        v
                                        for k, v in fact_dict.items()
                                        if "nombre" in k or k == "usuario"
                                    ),
                                    None,
                                )
                                if name_val:
                                    profile_parts.append(f"Nombre: {name_val}")

                                age_val = next(
                                    (
                                        v
                                        for k, v in fact_dict.items()
                                        if "edad" in k or "anos" in k or "anios" in k
                                    ),
                                    None,
                                )
                                if age_val:
                                    profile_parts.append(f"Edad: {age_val}")

                                city_val = next(
                                    (
                                        v
                                        for k, v in fact_dict.items()
                                        if "ciudad" in k
                                        or "vivo" in k
                                        or "residencia" in k
                                        or "ubicacion" in k
                                    ),
                                    None,
                                )
                                if city_val:
                                    profile_parts.append(f"Ciudad: {city_val}")

                                act_val = next(
                                    (
                                        v
                                        for k, v in fact_dict.items()
                                        if "actividad" in k or "estudio" in k or "carrera" in k
                                    ),
                                    None,
                                )
                                if act_val:
                                    profile_parts.append(f"Actividad: {act_val}")

                                if profile_parts:
                                    ans = "Perfil de usuario: " + " | ".join(profile_parts) + "."
                                    print(
                                        "  ⚡ [FAST-PATH]: Perfil estructurado de memoria "
                                        "(0 llamadas LLM)"
                                    )
                                    print(f"[AURA]: {ans}")
                                    t_tts_ms, t_playback_ms = self._speak(ans)
                                    memory_answered = True

                            if not memory_answered and top_fact and top_fact.confidence >= 0.50:
                                from ..memory.retrieval import normalize_text

                                norm_pred = normalize_text(top_fact.predicate)
                                val = top_fact.object_val

                                if "edad" in norm_pred or "anos" in norm_pred:
                                    ans = f"Tienes {val} años."
                                elif "ciudad" in norm_pred or "vivo" in norm_pred:
                                    ans = f"Vives en {val}."
                                elif "nombre" in norm_pred:
                                    ans = f"Tu nombre es {val}."
                                elif (
                                    "ocupacion" in norm_pred
                                    or "trabajo" in norm_pred
                                    or "profesion" in norm_pred
                                    or "empleo" in norm_pred
                                ):
                                    ans = f"Trabajas como {val}."
                                else:
                                    ans = f"Tu {top_fact.predicate} es {val}."

                                print(
                                    "  ⚡ [FAST-PATH]: Hecho recuperado de memoria "
                                    f"(0 llamadas LLM, conf={top_fact.confidence:.2f})"
                                )
                                print(f"[AURA]: {ans}")
                                t_tts_ms, t_playback_ms = self._speak(ans)
                                memory_answered = True
                            elif not memory_answered and top_pref:
                                ans = f"Tu preferencia para {top_pref.key} es {top_pref.value}."
                                print(
                                    "  ⚡ [FAST-PATH]: Preferencia recuperada de memoria "
                                    "(0 llamadas LLM)"
                                )
                                print(f"[AURA]: {ans}")
                                t_tts_ms, t_playback_ms = self._speak(ans)
                                memory_answered = True

                    if memory_answered:
                        telemetry.increment("fastpath_memory_queries")
                        telemetry.record_interaction(user_text, "FASTPATH_MEMORY")
                        continue

                t_intent_ms = (time.perf_counter() - t_intent_0) * 1000

                # 5. Cognitive decision & response (Single-pass when cognition available)
                t_llm_0 = time.perf_counter()
                if self.cognition is not None:
                    cognition_result = self.cognition.process_cognitive_cycle(user_text)
                    t_llm_ms = (time.perf_counter() - t_llm_0) * 1000
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
                        t_tts_ms, t_playback_ms = self._speak(response_text)
                    elif action == "IGNORE":
                        print("  🤫 [AURA decidió guardar silencio]")
                else:
                    decision = self._make_decision(user_text)
                    t_llm_ms = (time.perf_counter() - t_llm_0) * 1000

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
                            t_tts_ms, t_playback_ms = self._speak(response_text)

                        reminder = decision.get("reminder")
                        if isinstance(reminder, dict):
                            self._schedule_reminder(reminder)

                    elif action == "IGNORE":
                        print("  🤫 [AURA decidió guardar silencio]")

            except Exception as exc:
                telemetry.increment("voice_turn_failures")
                print(f"  [ERROR] Fallo en ciclo de voz: {exc}")
                time.sleep(0.3)
            finally:
                if t_turn_start > 0:
                    t_total_ms = (time.perf_counter() - t_turn_start) * 1000
                    sum_known = (
                        t_vad_ms
                        + t_stt_ms
                        + t_intent_ms
                        + t_retrieval_ms
                        + t_llm_ms
                        + t_tts_ms
                        + t_playback_ms
                    )
                    t_queue_ms = max(0.0, t_total_ms - sum_known)
                    self._log_pipeline_metrics(
                        t_vad_ms,
                        t_stt_ms,
                        t_intent_ms,
                        t_retrieval_ms,
                        t_llm_ms,
                        t_tts_ms,
                        t_playback_ms,
                        t_queue_ms,
                        t_total_ms,
                    )
                    telemetry.record_latency("time_turn_ms", t_total_ms)

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
            print(f"\n  [RECORDATORIO AURA]: {msg}")
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

    def _speak(self, text: str) -> tuple[float, float]:
        """Speaks text using TTS with thread-safe lock, returning (tts_synth_ms, playback_ms)."""
        with self._speech_lock:
            self._is_speaking = True
        t_synth_ms = 0.0
        t_play_ms = 0.0
        try:
            self.last_tts_output = text.strip().lower()
            t0 = time.perf_counter()
            res = self.tts.synthesize(text)
            t_synth_ms = (time.perf_counter() - t0) * 1000
            if res.audio_bytes:
                t1 = time.perf_counter()
                if hasattr(self.tts, "_play_fallback"):
                    self.tts._play_fallback(res.audio_bytes)
                else:
                    from .output import SoundDeviceOutputProvider

                    SoundDeviceOutputProvider().play(res.audio_bytes)
                t_play_ms = (time.perf_counter() - t1) * 1000
        finally:
            time.sleep(self.POST_TTS_COOLDOWN_SEC)
            self.last_tts_end = time.perf_counter()
            with self._speech_lock:
                self._is_speaking = False
        return t_synth_ms, t_play_ms
