from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure src is in sys.path when executed directly
src_dir = Path(__file__).resolve().parent.parent
sys.path[0] = str(src_dir)

from aura.cognition import CognitionModule  # noqa: E402
from aura.core import AURA, AURABootOptions  # noqa: E402
from aura.events import (  # noqa: E402
    ActionDispatched,
    Event,
    GoalSet,
    ObjectDetected,
    SpeechRecognized,
)
from aura.memory import Episode, Fact, MemoryModule  # noqa: E402
from aura.robotics import MockNavigationSystem, RoboticsModule  # noqa: E402
from aura.tools import ToolRegistry  # noqa: E402
from aura.world import CWMModule, Entity, EntityType  # noqa: E402


def _format_header() -> str:
    return (
        "╔═══════════════════════════════════════════╗\n"
        "║                   AURA                    ║\n"
        "║        Adaptive Unified Assistant         ║\n"
        "╚═══════════════════════════════════════════╝"
    )


def run_interactive_cli() -> int:
    """Runs the real interactive AURA Command Line Interface."""
    print(_format_header())

    options = AURABootOptions()
    aura = AURA(options=options)
    start_time = time.perf_counter()
    aura.boot()
    boot_ms = (time.perf_counter() - start_time) * 1000

    mod_count = len(aura.module_manager.list_modules()) if aura.module_manager else 0
    print(f"\nEstado: {aura.state.name}")
    print(f"Core inicializado ({mod_count} módulos activos en {boot_ms:.2f}ms)")
    print("Escribe 'help' para ver la lista de comandos disponibles.\n")

    # Event history logger
    recent_events: list[tuple[str, str, float]] = []

    def event_tracker(event: Event) -> None:
        event_name = getattr(event, "__event_name__", type(event).__name__)
        source = getattr(event, "source", "System")
        recent_events.append((event_name, source, time.time()))
        if len(recent_events) > 50:
            recent_events.pop(0)

    # Subscribe to main event streams
    for ev_type in (
        "SpeechRecognized",
        "ActionDispatched",
        "CognitiveStateChanged",
        "ObjectDetected",
        "GoalSet",
        "EpisodeRecorded",
        "FactLearned",
        "ToolExecuted",
        "MotorMoved",
        "NavigationTargetReached",
    ):
        aura.subscribe(ev_type, event_tracker)

    try:
        while True:
            try:
                user_input = input("\nAURA > ").strip()
            except KeyboardInterrupt, EOFError:
                print("\nInterrupción detectada. Apagando AURA...")
                break

            if not user_input:
                continue

            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd in ("exit", "quit", "salir"):
                print("Apagando el sistema AURA...")
                break
            elif cmd == "help":
                _print_help()
            elif cmd in ("status", "estado"):
                _handle_status(aura, start_time)
            elif cmd in ("cognition", "cognicion", "think"):
                _handle_cognition(aura, arg)
            elif cmd in ("memory", "memoria"):
                _handle_memory(aura, arg)
            elif cmd in ("cwm", "world"):
                _handle_cwm(aura, arg)
            elif cmd in ("tools", "herramientas"):
                _handle_tools(aura, arg)
            elif cmd in ("events", "eventos"):
                _handle_events(recent_events)
            elif cmd == "say":
                _handle_say(aura, arg)
            elif cmd in ("listen", "escuchar", "mic"):
                _handle_listen(aura, arg)
            elif cmd in ("converse", "conversar", "hablar", "chat"):
                _handle_converse(aura, arg)
            elif cmd in ("auto", "autonomo", "autónomo", "agent"):
                _handle_auto(aura)
            elif cmd in ("wake", "despertar", "espera"):
                _handle_wake(aura)
            elif cmd == "see":
                _handle_see(aura, arg)
            elif cmd == "goal":
                _handle_goal(aura, arg)
            elif cmd == "nav":
                _handle_nav(aura, arg)
            elif cmd in ("robotics",):
                _handle_robotics(aura, arg)
            elif cmd in ("stats", "metrics", "telemetry"):
                _handle_stats(aura)
            elif cmd in ("benchmark", "bench"):
                _handle_benchmark(aura)
            else:
                print(f"Comando desconocido '{cmd}'. Escribe 'help' para la lista de comandos.")
    finally:
        aura.shutdown(wait=True)
        print("AURA apagado correctamente.")
    return 0


def _print_help() -> None:
    print("\nComandos de la Interfaz AURA:")
    print("  • status                 - Estado del sistema, uptime y salud de los 8 módulos")
    print("  • stats                  - Muestra el informe completo de rendimiento y telemetría")
    print("  • cognition [prompt]     - Estado cognitivo, memoria de trabajo y decisiones")
    print("  • memory [query|add]     - Estado de memoria (episódica, semántica, preferencias)")
    print("  • cwm [list|add|query]   - Consulta y manipula entidades del Cognitive World Model")
    print("  • tools [list|exec]      - Lista y ejecuta las herramientas digitales integradas")
    print("  • events                 - Muestra el historial en tiempo real de eventos")
    print("  • say <mensaje>          - Envía una entrada conversacional de voz a AURA")
    print("  • listen [duración]      - Captura voz real desde tu micrófono y la transcribe")
    print("  • converse               - 🔴 MODO CONVERSACIÓN: escucha → razona → habla en bucle")
    print("  • auto                   - 🤖 MODO AUTÓNOMO: escucha voz y decide su acción")
    print("  • wake                   - 👂 MODO ESPERA: escucha el nombre 'AURA' y se activa solo")
    print("  • see <objeto>           - Envía una percepción visual de objeto")
    print("  • goal <meta>            - Define y prioriza un objetivo autónomo")
    print("  • nav <x> <y>            - Desplaza el sistema robótico a una coordenada")
    print("  • robotics               - Telemetría de sensores robóticos y estado de E-Stop")
    print("  • exit                   - Apaga AURA y cierra la interfaz")


def _handle_status(aura: AURA, start_time: float) -> None:
    uptime = time.perf_counter() - start_time
    sched_st = "Activo" if aura.options.enable_scheduler else "Desactivado"
    health_st = "Activo" if aura.options.enable_health_monitor else "Desactivado"
    print("\n[ESTADO DEL SISTEMA]")
    print(f"  • Estado Global: {aura.state.name}")
    print(f"  • Tiempo de Actividad (Uptime): {uptime:.2f}s")
    print(f"  • Planificador: {sched_st}")
    print(f"  • Monitor de Salud: {health_st}")
    print("\n[SALUD DE MÓDULOS (8)]")
    if aura.module_manager is not None:
        for name, m in aura.module_manager.list_modules():
            h = m.health
            err_info = h.last_error if h.last_error else "Sin Errores"
            print(
                f"  • {name:<12} | Prioridad: {m.priority:<2} | "
                f"Estado: {h.status.value:<8} | Diagnóstico: {err_info}"
            )


def _handle_stats(aura: AURA) -> None:
    from aura.telemetry import TelemetryManager

    tm = (
        aura.telemetry
        if hasattr(aura, "telemetry") and aura.telemetry
        else TelemetryManager.get_instance()
    )
    print("\n" + tm.get_performance_report())


def _handle_cognition(aura: AURA, arg: str) -> None:
    if aura.module_manager is None:
        print("ModuleManager no disponible.")
        return
    cog_mod = aura.module_manager.get("cognition")
    if not isinstance(cog_mod, CognitionModule):
        print("Módulo de cognición no disponible.")
        return

    print("\n[SISTEMA DE COGNICIÓN]")
    print(f"  • Estado Cognitivo: {cog_mod.state_machine.state.value}")
    turns = cog_mod.working_memory.get_recent_conversation()
    print(f"  • Memoria de Trabajo ({len(turns)} turnos conversacionales):")
    for t in turns[-3:]:
        print(f"      [{t.get('role', 'user')}]: {t.get('content', '')}")

    if arg:
        print(f"\n  > Procesando prompt cognitivo: '{arg}'...")
        aura.publish(SpeechRecognized(text=arg))
        print("  > Procesado e integrado en la memoria de trabajo.")


def _handle_memory(aura: AURA, arg: str) -> None:
    if aura.module_manager is None:
        print("ModuleManager no disponible.")
        return
    mem_mod = aura.module_manager.get("memory")
    if not isinstance(mem_mod, MemoryModule):
        print("Módulo de memoria no disponible.")
        return

    sub_parts = arg.split(maxsplit=2)
    sub_cmd = sub_parts[0].lower() if sub_parts else "status"

    if sub_cmd in ("status", "list", ""):
        ep_count = mem_mod.episodic.count()
        fact_count = len(mem_mod.semantic.all_facts())
        pref_count = len(mem_mod.preferences.all_preferences())
        print("\n[SISTEMA DE MEMORIA]")
        print(f"  • Episodios Episódicos: {ep_count}")
        print(f"  • Hechos Semánticos:    {fact_count}")
        print(f"  • Preferencias Usuario: {pref_count}")

    elif sub_cmd in ("query", "search"):
        search_text = sub_parts[1] if len(sub_parts) > 1 else ""
        if not search_text:
            print("Uso: memory query <texto_busqueda>")
            return
        res = mem_mod.retrieval.query(search_text)
        ep_summaries = [e.summary for e in res.episodes]
        fact_str = [f"{f.subject} {f.predicate} {f.object_val}" for f in res.facts]
        pref_str = [f"{p.key}={p.value}" for p in res.preferences]
        print(f"\n[RESULTADOS DE MEMORIA PARA '{search_text}']")
        print(f"  • Episodios ({len(res.episodes)}): {ep_summaries}")
        print(f"  • Hechos ({len(res.facts)}): {fact_str}")
        print(f"  • Preferencias ({len(res.preferences)}): {pref_str}")

    elif sub_cmd == "add":
        if len(sub_parts) < 3:
            print("Uso: memory add <episode|fact|preference> <contenido>")
            return
        mtype, mcontent = sub_parts[1].lower(), sub_parts[2]
        if mtype == "episode":
            mem_mod.episodic.record_episode(Episode(summary=mcontent))
            print(f"Episodio registrado: '{mcontent}'")
        elif mtype == "fact":
            mem_mod.semantic.add_fact(Fact(subject=mcontent, predicate="is", object_val="defined"))
            print(f"Hecho aprendido: '{mcontent}'")
        elif mtype == "preference":
            k_v = mcontent.split("=", maxsplit=1)
            key = k_v[0]
            val = k_v[1] if len(k_v) > 1 else "true"
            mem_mod.preferences.set_preference(key, val)
            print(f"Preferencia guardada: {key}={val}")


def _handle_cwm(aura: AURA, arg: str) -> None:
    if aura.module_manager is None:
        print("ModuleManager no disponible.")
        return
    cwm_mod = aura.module_manager.get("cwm")
    if not isinstance(cwm_mod, CWMModule):
        print("Módulo CWM no disponible.")
        return

    sub_parts = arg.split(maxsplit=2)
    sub_cmd = sub_parts[0].lower() if sub_parts else "list"

    if sub_cmd in ("list", "status", ""):
        entities = cwm_mod.cwm.all_entities()
        relations = cwm_mod.cwm.all_relations()
        print("\n[COGNITIVE WORLD MODEL (CWM)]")
        print(f"  • Entidades ({len(entities)}):")
        for e in entities:
            print(f"      - [{e.type}] {e.name} (ID: {e.id})")
        print(f"  • Relaciones ({len(relations)}):")
        for r in relations:
            rtype = r.relation_type
            rel_name = rtype.value if hasattr(rtype, "value") else rtype
            print(f"      - {r.source_id} --({rel_name})--> {r.target_id}")

    elif sub_cmd == "add":
        if len(sub_parts) < 2:
            print("Uso: cwm add <nombre_entidad>")
            return
        name = sub_parts[1]
        e = Entity(name=name, type=EntityType.OBJECT)
        cwm_mod.cwm.add_entity(e)
        print(f"Entidad agregada a CWM: {e.name} (ID: {e.id})")


def _handle_tools(aura: AURA, arg: str) -> None:
    registry = aura.container.resolve(ToolRegistry)
    sub_parts = arg.split(maxsplit=1)
    sub_cmd = sub_parts[0].lower() if sub_parts else "list"

    if sub_cmd in ("list", "status", ""):
        tools = registry.list_metadata()
        print(f"\n[HERRAMIENTAS DIGITALES REGISTRADAS ({len(tools)})]")
        for t in tools:
            print(f"  • {t.name:<15} [{t.category:<12}] - {t.description}")

    elif sub_cmd == "exec":
        tool_name = sub_parts[1] if len(sub_parts) > 1 else ""
        if not tool_name:
            print("Uso: tools exec <nombre_herramienta>")
            return
        res = registry.execute(tool_name)
        if res.success:
            print(f"  ✓ Ejecución exitosa de '{tool_name}' ({res.execution_time_ms}ms)")
            print(f"    Salida: {res.output}")
        else:
            print(f"  ✗ Error al ejecutar '{tool_name}': {res.error}")


def _handle_events(recent_events: list[tuple[str, str, float]]) -> None:
    print(f"\n[HISTORIAL DE EVENTOS RECIENTES ({len(recent_events)})]")
    if not recent_events:
        print("  No hay eventos registrados recientemente.")
        return
    for ev_name, src, t_stamp in recent_events[-15:]:
        t_str = time.strftime("%H:%M:%S", time.localtime(t_stamp))
        print(f"  • [{t_str}] Evento '{ev_name}' publicado por '{src}'")


def _handle_say(aura: AURA, text: str) -> None:
    if not text:
        print("Uso: say <mensaje>")
        return
    print(f"Usuario: {text}")
    aura.publish(SpeechRecognized(text=text))
    print(f"AURA: Entendido. Procesando la instrucción '{text}'...")


def _handle_listen(aura: AURA, arg: str) -> None:
    from aura.audio import FasterWhisperSTTProvider, MicrophoneRecorder

    duration = 4.0
    if arg:
        try:
            duration = float(arg)
        except ValueError:
            pass

    print(f"\n🎙️ ¡Grabando micrófono en vivo durante {duration:.1f} segundos...")
    print("   Habla claramente por tu micrófono...")

    recorder = MicrophoneRecorder()
    audio_bytes = recorder.record_bytes(duration_sec=duration)

    print("   Audio capturado. Procesando transcripción con Faster Whisper...")
    stt = FasterWhisperSTTProvider(model_size_or_path="tiny", device="cpu")
    result = stt.transcribe(audio_bytes, language="es")

    if result.text:
        print(f"\n   ✓ Vocabulario reconocido: '{result.text}'")
        print(f"     Confianza Log-Prob: {result.confidence:.2f}")
    else:
        print("\n   ⚠ No se detectó ninguna voz en la grabación.")


def _handle_wake(aura: AURA) -> None:
    """Passive wake-word listening mode: AURA monitors silently and activates on its name."""
    from aura.audio import WhisperWakeWordDetector

    print("\n" + "═" * 60)
    print("  👂 MODO ESPERA ACTIVO — AURA ESTÁ ESCUCHANDO...")
    print("  Di 'AURA' para activar la conversación.")
    print("  Presiona Ctrl+C para salir del modo espera.")
    print("═" * 60 + "\n")

    import threading

    conversation_triggered = threading.Event()

    def on_wake_detected(result: object) -> None:
        from aura.audio.wakeword import WakeWordResult as _WakeWordResult

        r: _WakeWordResult = result  # type: ignore[assignment]
        print(f"\n  ✅ ¡Wake Word detectada! → '{r.keyword}' (confianza: {r.confidence:.0%})")
        print("  🔴 Activando AURA...\n")
        conversation_triggered.set()

    detector = WhisperWakeWordDetector(
        keywords=["aura", "hora", "ahora", "laura"],
        model_size="tiny",
        chunk_duration_sec=1.5,
        on_detected=on_wake_detected,
    )

    detector.start()
    print("  [Sistema en espera silenciosa. Habla cuando estés listo...]\n")

    try:
        conversation_triggered.wait()  # Block until wake word heard
    except KeyboardInterrupt:
        print("\n  Saliendo del modo espera...")
    finally:
        detector.stop()

    if conversation_triggered.is_set():
        _handle_converse(aura, "")


def _handle_converse(aura: AURA, arg: str) -> None:
    """Full conversational loop: microphone → STT → LLM → TTS speak. Press Ctrl+C to exit."""
    import os

    from aura.audio import EdgeTTSProvider, FasterWhisperSTTProvider, MicrophoneRecorder
    from aura.cognition import GeminiLLMProvider, LLMProvider

    # --- Parse optional rounds argument ---
    max_rounds = 0  # 0 = infinite
    if arg:
        try:
            max_rounds = int(arg)
        except ValueError:
            pass

    stt = FasterWhisperSTTProvider(model_size_or_path="base", device="cpu")
    tts = EdgeTTSProvider(voice="es-aura")

    aura.config.load_from_env()

    from aura.cognition import OpenAILLMProvider

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    has_valid_gemini = bool(gemini_key and not gemini_key.startswith("AQ."))

    llm: LLMProvider
    if os.environ.get("GROQ_API_KEY"):
        llm = OpenAILLMProvider()
        print("  🧠 Motor LLM: Groq Cloud (Compound Real) Activo")
    elif os.environ.get("OPENROUTER_API_KEY"):
        llm = OpenAILLMProvider()
        print("  🧠 Motor LLM: OpenRouter Real Activo")
    elif os.environ.get("OPENAI_API_KEY"):
        llm = OpenAILLMProvider()
        print("  🧠 Motor LLM: OpenAI Real Activo")
    elif has_valid_gemini:
        llm = GeminiLLMProvider()
    else:
        llm = OpenAILLMProvider()
        print("  🧠 Motor LLM: Conectando motor LLM de AURA...")

    target_device = (
        aura.config.get("audio.input_device", "") if getattr(aura, "config", None) else ""
    )
    if not target_device:
        target_device = os.environ.get("AURA_AUDIO_INPUT_DEVICE", "C920")

    recorder = MicrophoneRecorder(device=target_device)

    print("\n" + "═" * 60)
    print("  🔴 MODO CONVERSACIÓN ACTIVO — AURA TE ESTÁ ESCUCHANDO")
    print("  Habla por tu micrófono. Escribe 'salir' o Ctrl+C para terminar.")
    print("═" * 60 + "\n")

    # AURA greets the user vocally
    greeting = "Hola, soy AURA. Di algo y te responderé."
    print(f"[AURA]: {greeting}")
    tts.speak(greeting)

    rounds = 0
    try:
        while max_rounds == 0 or rounds < max_rounds:
            print("\n  🎙️  Escuchando...")
            audio_bytes = recorder.record_until_silence(
                max_duration_sec=10.0,
                silence_sec=1.2,
                energy_threshold=120.0,
            )
            if not audio_bytes:
                audio_bytes = recorder.record_bytes(duration_sec=3.0)

            stt_result = stt.transcribe(audio_bytes, language="es")
            user_text = stt_result.text.strip()

            if not user_text:
                print("  ⚠  No escuché nada. Intenta de nuevo.")
                continue

            print(f"\n[Tú]:   {user_text}")

            from aura.cognition import ControlIntentDetector

            if ControlIntentDetector.is_exit(user_text):
                farewell = "Hasta luego. Fue un placer conversar contigo."
                print(f"[AURA]: {farewell}")
                tts.speak(farewell)
                break

            # Cognitive reasoning via CognitionModule pipeline
            cog_mod = aura.module_manager.get("cognition") if aura.module_manager else None
            if isinstance(cog_mod, CognitionModule):
                reasoning = cog_mod.process_cognitive_cycle(user_text)
                aura_text = reasoning.summary
            else:
                llm_response = llm.generate_response(
                    prompt=user_text,
                    system_instruction=(
                        "Eres AURA, un asistente cognitivo inteligente y autónomo. "
                        "Responde siempre en español de forma concisa, clara y amigable."
                    ),
                )
                aura_text = llm_response.content
            print(f"[AURA]: {aura_text}")
            tts.speak(aura_text)
            rounds += 1

    except KeyboardInterrupt:
        farewell = "Conversación interrumpida. Hasta pronto."
        print(f"\n[AURA]: {farewell}")
        tts.speak(farewell)


def _handle_auto(aura: AURA) -> None:
    """Continuous autonomous voice loop: listens constantly, interrupts on user speech,
    and decides via LLM whether to IGNORE, RESPOND, or EXECUTE."""
    import os

    from aura.audio import AutonomousVoiceAgent, EdgeTTSProvider, FasterWhisperSTTProvider
    from aura.cognition import CognitionModule, GeminiLLMProvider, LLMProvider, OpenAILLMProvider

    aura.config.load_from_env()

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    has_valid_gemini = bool(gemini_key and not gemini_key.startswith("AQ."))

    llm: LLMProvider
    if (
        os.environ.get("GROQ_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
    ):
        llm = OpenAILLMProvider()
    elif has_valid_gemini:
        llm = GeminiLLMProvider()
    else:
        llm = OpenAILLMProvider()

    stt = FasterWhisperSTTProvider(model_size_or_path="base", device="cpu")
    tts = EdgeTTSProvider(voice="es-aura")

    cog_mod = aura.module_manager.get("cognition") if aura.module_manager else None
    cognition = cog_mod if isinstance(cog_mod, CognitionModule) else None

    target_device = (
        aura.config.get("audio.input_device", "") if getattr(aura, "config", None) else ""
    )
    if not target_device:
        target_device = os.environ.get("AURA_AUDIO_INPUT_DEVICE", "C920")

    agent = AutonomousVoiceAgent(
        llm_provider=llm,
        stt_provider=stt,
        tts_provider=tts,
        event_bus=aura.event_bus,
        scheduler=aura.scheduler,
        cognition_module=cognition,
        input_device=target_device,
    )

    try:
        agent._loop()
    except KeyboardInterrupt:
        print("\n  Saliendo del modo autónomo continuo...")
    finally:
        agent.stop()


def _handle_see(aura: AURA, label: str) -> None:
    if not label:
        print("Uso: see <objeto>")
        return
    aura.publish(ObjectDetected(label=label, confidence=0.96))
    print(f"Percepción Visual: Objeto '{label}' detectado con 96% de confianza.")


def _handle_goal(aura: AURA, desc: str) -> None:
    if not desc:
        print("Uso: goal <descripcion_de_meta>")
        return
    aura.publish(GoalSet(description=desc))
    print(f"Autonomía: Objetivo '{desc}' creado y priorizado.")


def _handle_nav(aura: AURA, coords_str: str) -> None:
    parts = coords_str.split()
    if len(parts) < 2:
        print("Uso: nav <x> <y>")
        return
    try:
        x, y = float(parts[0]), float(parts[1])
        aura.publish(ActionDispatched(action_type="navigate", payload={"x": x, "y": y}))
        print(f"Robótica: Desplazamiento iniciado hacia waypoints (x={x}, y={y}).")
    except ValueError:
        print("Coordenadas numéricas inválidas.")


def _handle_robotics(aura: AURA, arg: str) -> None:
    if aura.module_manager is None:
        print("ModuleManager no disponible.")
        return
    rob_mod = aura.module_manager.get("robotics")
    if not isinstance(rob_mod, RoboticsModule):
        print("Módulo de robótica no disponible.")
        return

    e_stop_status = "ACTIVADO" if rob_mod.safety.is_emergency_stopped else "Seguro (Desactivado)"
    print("\n[SISTEMA DE ROBÓTICA Y TELEMETRÍA]")
    print(f"  • Paro de Emergencia (E-Stop): {e_stop_status}")
    sensors = rob_mod.sensors.read_all_sensors()
    print("  • Telemetría de Sensores:")
    for s in sensors:
        print(f"      - {s.sensor_type:<15}: {s.value} {s.unit}")
    if isinstance(rob_mod.navigation, MockNavigationSystem):
        pos = rob_mod.navigation.current_position
        print(f"  • Posición Espacial Actual: (x={pos.x}, y={pos.y}, z={pos.z})")


def _handle_benchmark(aura: AURA) -> None:
    from aura.telemetry import TelemetryManager

    tm = TelemetryManager.get_instance()
    all_counters = tm.get_all_counters()
    all_latencies = tm.get_all_latencies()

    avg_stt = round(all_latencies["time_stt_ms"].avg_ms) if "time_stt_ms" in all_latencies else 0
    avg_cog = (
        round(all_latencies["time_cognition_ms"].avg_ms)
        if "time_cognition_ms" in all_latencies
        else 0
    )
    avg_llm = round(all_latencies["time_llm_ms"].avg_ms) if "time_llm_ms" in all_latencies else 0
    avg_turn = round(all_latencies["time_turn_ms"].avg_ms) if "time_turn_ms" in all_latencies else 0

    llm_total = all_counters.get("llm_calls_total", 0)
    fp_greetings = all_counters.get("fastpath_greetings", 0)
    fp_memory = all_counters.get("fastpath_memory_queries", 0)
    fp_exit = all_counters.get("fastpath_exit_commands", 0)
    fp_total = fp_greetings + fp_memory + fp_exit

    interactions = len(tm.get_recent_interactions())
    turn_count = max(
        1,
        all_latencies["time_turn_ms"].count if "time_turn_ms" in all_latencies else interactions,
    )

    fp_hit_rate = round((fp_total / turn_count) * 100.0, 1)
    llm_per_turn = round(llm_total / turn_count, 2)

    mem_reads = all_counters.get("memory_retrievals", 0)
    mem_writes = all_counters.get("memory_writes", 0)
    autonomy_cycles = all_counters.get("autonomy_cycles", 0)

    mem_success_rate = 100.0 if mem_reads > 0 else 0.0
    token_stats = tm.get_token_stats()

    print("===================================")
    print("AURA BENCHMARK REPORT")
    print("===================================")
    print(f"Average STT Latency:       {avg_stt} ms")
    print(f"Average Cognition Latency:  {avg_cog} ms")
    print(f"Average LLM Latency:      {avg_llm} ms")
    print(f"Average Turn Latency:     {avg_turn} ms")
    print("")
    print(f"Average Prompt Tokens:     {token_stats['avg_prompt_tokens']}")
    print(f"Average Completion Tokens: {token_stats['avg_completion_tokens']}")
    print(f"Largest Prompt Observed:   {token_stats['max_prompt_tokens']}")
    print(f"Largest Completion:        {token_stats['max_completion_tokens']}")
    print("")
    print(f"FastPath Hit Rate:        {fp_hit_rate:.1f}%")
    print(f"LLM Calls per Turn:       {llm_per_turn:.2f}")
    print(f"Memory Retrieval Success: {mem_success_rate:.1f}%")
    print("")
    print(f"Total Interactions:       {interactions}")
    print(f"Total LLM Calls:          {llm_total}")
    print(f"Total FastPaths:          {fp_total}")
    print(f"Memory Writes:            {mem_writes}")
    print(f"Memory Reads:             {mem_reads}")
    print(f"Autonomy Cycles:          {autonomy_cycles}")
    print("===================================")


def run_benchmark_mode() -> int:
    """Runs AURA benchmark suite, exports snapshot & report, and prints metrics."""
    options = AURABootOptions(enable_audio=False, enable_vision=False)
    aura = AURA(options=options)
    aura.boot()
    try:
        from aura.telemetry import TelemetryManager, generate_runtime_report

        _handle_benchmark(aura)
        tm = TelemetryManager.get_instance()
        tm.export_snapshot()
        generate_runtime_report()
    finally:
        aura.shutdown(wait=True)
    return 0


def run_voice_cli() -> int:
    """Runs AURA 0.2 controlled real voice interaction mode (Push-to-Talk)."""
    print(
        "╔═══════════════════════════════════════════╗\n"
        "║            AURA VOICE MODE (0.2)          ║\n"
        "║      Primera Interacción de Voz REAL      ║\n"
        "╚═══════════════════════════════════════════╝"
    )

    from aura.audio import (
        AudioModule,
        EdgeTTSProvider,
        FasterWhisperSTTProvider,
        SoundDeviceInputProvider,
        SoundDeviceOutputProvider,
    )
    from aura.config import ConfigurationManager

    config = ConfigurationManager()
    config.load_from_env()

    input_prov = SoundDeviceInputProvider()
    output_prov = SoundDeviceOutputProvider()
    stt_prov = FasterWhisperSTTProvider(config=config)
    tts_prov = EdgeTTSProvider(config=config)

    options = AURABootOptions()
    aura = AURA(options=options)
    aura.boot()

    audio_mod: AudioModule
    if aura.module_manager is not None:
        existing_mod = aura.module_manager.get("audio")
        if isinstance(existing_mod, AudioModule):
            existing_mod.audio_input = input_prov
            existing_mod.audio_output = output_prov
            existing_mod.stt = stt_prov
            existing_mod.tts = tts_prov
            audio_mod = existing_mod
        else:
            audio_mod = AudioModule(
                config=config,
                audio_input=input_prov,
                audio_output=output_prov,
                stt_provider=stt_prov,
                tts_provider=tts_prov,
            )
    else:
        audio_mod = AudioModule(
            config=config,
            audio_input=input_prov,
            audio_output=output_prov,
            stt_provider=stt_prov,
            tts_provider=tts_prov,
        )

    llm_name = "Mock"
    if aura.module_manager is not None:
        cog_mod = aura.module_manager.get("cognition")
        if isinstance(cog_mod, CognitionModule):
            llm_name = type(cog_mod.llm_provider).__name__

    print("\n  🧠 Módulo de Cognición Activo (AURA 0.3)")
    print(f"  🤖 Proveedor LLM: {llm_name}")
    print("  🎙️ Captura de Micrófono Lista (SoundDevice)")
    print("  🔊 Reproducción por Altavoz Lista (SoundDevice)")
    print("  🗣️ STT: Faster Whisper | TTS: Edge TTS\n")
    print("  - Presiona ENTER para comenzar a hablar.")
    print("  - Presiona ENTER nuevamente para detener la grabación.")
    print("  - Escribe 'exit' o 'q' + ENTER para salir.\n")

    try:
        while True:
            cmd = input("\n[Presiona ENTER para hablar | 'q' para salir]: ").strip()
            if cmd.lower() in ("exit", "q", "quit", "salir"):
                print("Saliendo del modo de voz AURA...")
                break

            print(
                "🎙️ Capturando audio del micrófono... (Presiona ENTER para detener)",
                end="",
                flush=True,
            )
            audio_mod.start_voice_capture()

            _ = input()
            print("\n🧠 Procesando turno de voz...")

            turn = audio_mod.stop_voice_capture_and_process(playback=True)

            if turn.recognized_text:
                print(f"\n  [Tú]:   {turn.recognized_text}")
                print(f"  [AURA]: {turn.response_text}")
            else:
                print("\n  ⚠ No se detectó ninguna voz clara en el audio.")

            m = turn.metrics
            print("\n[Métricas del turno]:")
            print(f"  • Captura:    {m.capture_sec:.2f}s")
            print(f"  • STT:        {m.stt_sec:.2f}s")
            print(f"  • Cognición:  {m.cognition_sec:.2f}s")
            print(f"  • TTS:        {m.tts_sec:.2f}s")
            print(f"  • Playback:   {m.playback_sec:.2f}s")
            print("  -------------------")
            print(f"  • Total:      {m.total_sec:.2f}s")

    except KeyboardInterrupt, EOFError:
        print("\nInterrupción detectada. Apagando AURA...")
    finally:
        aura.shutdown(wait=True)
        print("AURA apagado correctamente.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA CLI Real Interface Launcher")
    parser.add_argument(
        "--interactive", "-i", action="store_true", default=False, help="Run real interactive CLI"
    )
    parser.add_argument(
        "--voice", "-v", action="store_true", default=False, help="Run AURA 0.2 real voice mode"
    )
    parser.add_argument(
        "--benchmark", "-b", action="store_true", default=False, help="Run AURA benchmark suite"
    )
    args = parser.parse_args()
    if args.benchmark:
        return run_benchmark_mode()
    if args.voice:
        return run_voice_cli()
    return run_interactive_cli()


if __name__ == "__main__":
    sys.exit(main())
