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
            elif cmd == "see":
                _handle_see(aura, arg)
            elif cmd == "goal":
                _handle_goal(aura, arg)
            elif cmd == "nav":
                _handle_nav(aura, arg)
            elif cmd == "robotics":
                _handle_robotics(aura, arg)
            else:
                print(f"Comando desconocido '{cmd}'. Escribe 'help' para la lista de comandos.")
    finally:
        aura.shutdown(wait=True)
        print("AURA apagado correctamente.")
    return 0


def _print_help() -> None:
    print("\nComandos de la Interfaz AURA:")
    print("  • status                 - Estado del sistema, uptime y salud de los 8 módulos")
    print("  • cognition [prompt]     - Estado cognitivo, memoria de trabajo y decisiones")
    print("  • memory [query|add]     - Estado de memoria (episódica, semántica, preferencias)")
    print("  • cwm [list|add|query]   - Consulta y manipula entidades del Cognitive World Model")
    print("  • tools [list|exec]      - Lista y ejecuta las herramientas digitales integradas")
    print("  • events                 - Muestra el historial en tiempo real de eventos")
    print("  • say <mensaje>          - Envía una entrada conversacional de voz a AURA")
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


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA CLI Real Interface Launcher")
    parser.add_argument(
        "--interactive", "-i", action="store_true", default=True, help="Run real interactive CLI"
    )
    _ = parser.parse_args()
    return run_interactive_cli()


if __name__ == "__main__":
    sys.exit(main())
