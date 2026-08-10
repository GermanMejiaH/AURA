from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .edge_tts_provider import EdgeTTSProvider
from .faster_whisper_stt import FasterWhisperSTTProvider
from .microphone import MicrophoneRecorder

if TYPE_CHECKING:
    from ..cognition.provider import LLMProvider
    from ..events import EventBus


class AutonomousVoiceAgent:
    """Continuous Autonomous Voice Agent for AURA.

    Features:
    1. Continuous VAD: Monitors microphone constantly.
    2. Active Interruption: If user starts speaking while AURA speaks, AURA silences immediately.
    3. Cognitive Decision Making: LLM decides whether to (A) stay silent, (B) respond verbally,
       or (C) execute an autonomous action.
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
        on_decision: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.llm = llm_provider
        self.stt = stt_provider or FasterWhisperSTTProvider(model_size_or_path="base", device="cpu")
        self.tts = tts_provider or EdgeTTSProvider(voice="es-aura")
        self.event_bus = event_bus
        self.scheduler = scheduler
        self.on_decision = on_decision

        self.recorder = MicrophoneRecorder()
        self._running = False
        self._is_speaking = False
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
        if self._is_speaking:
            self._is_speaking = False
            self.tts.stop()
            print("\n  🤐 [AURA detectó tu voz y guardó silencio]")

    def _loop(self) -> None:
        """Continuous background loop: Listen VAD -> Transcribe -> Decide -> Act/Speak/Ignore."""
        self._running = True
        print("\n" + "═" * 65)
        print("  🧠 MODO AUTÓNOMO CONTINUO ACTIVO — AURA TE ESCUCHA Y DECIDE")
        print("  Habla libremente. AURA decidirá si responder, actuar o guardar silencio.")
        print("  Si AURA está hablando y empiezas a hablar, se callará de inmediato.")
        print("═" * 65 + "\n")

        greetings = "Modo autónomo activado. Estoy escuchando."
        print(f"[AURA]: {greetings}")
        self._speak(greetings)

        while self._running:
            try:
                # 1. Listen until user stops speaking
                audio_bytes = self.recorder.record_until_silence(
                    max_duration_sec=15.0,
                    silence_sec=1.2,
                    energy_threshold=180.0,
                )

                if not audio_bytes or len(audio_bytes) < 4000:
                    time.sleep(0.05)
                    continue

                # 2. Transcribe speech
                stt_res = self.stt.transcribe(audio_bytes, language="es")
                user_text = stt_res.text.strip()

                if not user_text:
                    continue

                # 3. Interruption check
                self.interrupt_speaking()

                print(f"\n[Voz Detectada]: '{user_text}'")

                # Check for exit phrase
                exit_words = ("desactivar modo autónomo", "detener autónomo", "salir")
                if any(w in user_text.lower() for w in exit_words):
                    farewell = "Desactivando modo autónomo continuo. Hasta luego."
                    print(f"[AURA]: {farewell}")
                    self._speak(farewell)
                    break

                # 4. Cognitive decision via LLM
                decision = self._make_decision(user_text)

                if self.on_decision is not None:
                    self.on_decision(decision)

                action = decision.get("action", "IGNORE")
                response_text = decision.get("response", "").strip()
                reasoning = decision.get("reasoning", "")

                print(f"  🤔 Decisión Cognitiva -> [{action}] ({reasoning})")

                if action in ("RESPOND", "EXECUTE") and response_text:
                    print(f"[AURA]: {response_text}")
                    self._speak(response_text)

                    # Handle reminders if requested
                    reminder = decision.get("reminder")
                    if isinstance(reminder, dict) and "delay_seconds" in reminder:
                        self._schedule_reminder(reminder)

                elif action == "IGNORE":
                    print("  🤫 [AURA decidió guardar silencio]")

            except Exception as exc:
                time.sleep(0.3)
                _ = exc

    def _schedule_reminder(self, reminder: dict[str, Any]) -> None:
        """Schedules a gentle reminder to trigger when time arrives."""
        delay = float(reminder.get("delay_seconds", 60))
        text = str(reminder.get("text", "Recordatorio"))
        if delay < 1.0:
            delay = 1.0

        def _notify() -> None:
            msg = f"Hola, te recuerdo suavemente: {text}."
            print(f"\n  ⏰ [RECORDATORIO AURA]: {msg}")
            self._speak(msg)

        if self.scheduler is not None and hasattr(self.scheduler, "schedule_once"):
            self.scheduler.schedule_once(
                name=f"Reminder_{text[:20]}",
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
        from datetime import datetime

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prompt = (
            f"Fecha y hora actual del sistema: {now_str}\n"
            f"Entrada de voz del usuario: '{text}'"
        )

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
        """Speaks text using TTS while flagging speaking state."""
        self._is_speaking = True
        try:
            self.tts.speak(text)
        finally:
            self._is_speaking = False
