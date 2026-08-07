from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def run_interactive_cli() -> int:
    """Runs the interactive AURA Command Line Interface."""
    src_dir = Path(__file__).resolve().parent.parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from aura.core import AURA, AURABootOptions
    from aura.events import ActionDispatched, GoalSet, ObjectDetected, SpeechRecognized
    from aura.tools import ToolRegistry
    print("=" * 60)
    print("      AURA — Autonomous Universal Responsive Agent CLI")
    print("=" * 60)
    print("Iniciando Core AURA con los 8 Módulos Cognitivos...")

    options = AURABootOptions()
    aura = AURA(options=options)
    start_t = time.perf_counter()
    aura.boot()
    boot_time = (time.perf_counter() - start_t) * 1000

    modules = aura.module_manager.list_modules() if aura.module_manager is not None else []
    print(f"\n[AURA READY] Estado: {aura.state.name} | Tiempo de arranque: {boot_time:.2f}ms")
    print(f"Módulos Activos ({len(modules)}): "
          f"{', '.join([name for name, _ in modules])}")
    print("\nEscribe 'help' para ver los comandos disponibles o 'exit' para salir.\n")

    try:
        while True:
            try:
                user_input = input("AURA> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nInterrupción detectada. Cerrando AURA...")
                break

            if not user_input:
                continue

            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd in ("exit", "quit"):
                print("Cerrando AURA...")
                break
            elif cmd == "help":
                print("\nComandos disponibles:")
                print("  status         - Muestra el estado del sistema y salud de módulos")
                print("  cwm            - Muestra las entidades en el Cognitive World Model")
                print("  tools          - Lista las herramientas digitales disponibles")
                print("  exec <tool>    - Ejecuta una herramienta digital (ej: exec browser_tool)")
                print("  say <texto>    - Envia una entrada de voz al sistema (SpeechRecognized)")
                print("  see <objeto>   - Envia una percepción visual (ObjectDetected)")
                print("  goal <texto>   - Crea un objetivo autónomo (GoalSet)")
                print("  nav <x> <y>    - Desplaza el cuerpo robótico a una coordenada")
                print("  exit           - Apaga AURA y sale de la consola\n")
            elif cmd == "status":
                print(f"Estado: {aura.state.name}")
                if aura.module_manager is not None:
                    for name, m in aura.module_manager.list_modules():
                        print(f"  • Módulo '{name}': Prioridad {m.priority}")
            elif cmd == "cwm":
                from aura.world import CWMModule

                cwm_mod = aura.container.resolve(CWMModule)
                entities = cwm_mod.cwm.all_entities()
                print(f"Cognitive World Model ({len(entities)} entidades):")
                for e in entities:
                    print(f"  • {e.name} [{e.type}] (ID: {e.id})")
            elif cmd == "tools":
                registry = aura.container.resolve(ToolRegistry)
                print(f"Herramientas Registradas ({len(registry.list_metadata())}):")
                for t in registry.list_metadata():
                    print(f"  • {t.name} [{t.category}]: {t.description}")
            elif cmd == "exec":
                if not arg:
                    print("Uso: exec <nombre_herramienta>")
                    continue
                registry = aura.container.resolve(ToolRegistry)
                res = registry.execute(arg)
                if res.success:
                    print(f"Salida: {res.output} ({res.execution_time_ms}ms)")
                else:
                    print(f"Error: {res.error}")
            elif cmd == "say":
                if not arg:
                    print("Uso: say <texto>")
                    continue
                aura.publish(SpeechRecognized(text=arg))
                print(f"Evento publicado: SpeechRecognized('{arg}')")
            elif cmd == "see":
                if not arg:
                    print("Uso: see <nombre_objeto>")
                    continue
                aura.publish(ObjectDetected(label=arg, confidence=0.95))
                print(f"Evento publicado: ObjectDetected(label='{arg}')")
            elif cmd == "goal":
                if not arg:
                    print("Uso: goal <descripcion>")
                    continue
                aura.publish(GoalSet(description=arg))
                print(f"Objetivo Autónomo Publicado: '{arg}'")
            elif cmd == "nav":
                coords = arg.split()
                if len(coords) < 2:
                    print("Uso: nav <x> <y>")
                    continue
                try:
                    x, y = float(coords[0]), float(coords[1])
                    aura.publish(ActionDispatched(action_type="navigate", payload={"x": x, "y": y}))
                    print(f"Navegación Robótica Despachada: (x={x}, y={y})")
                except ValueError:
                    print("Coordenadas no válidas.")
            else:
                print(f"Comando desconocido '{cmd}'. Escribe 'help' para ayuda.")
    finally:
        aura.shutdown(wait=True)
        print("AURA apagado correctamente.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA CLI Launcher")
    parser.add_argument(
        "--interactive", "-i", action="store_true", default=True, help="Run interactive CLI"
    )
    _ = parser.parse_args()
    return run_interactive_cli()


if __name__ == "__main__":
    sys.exit(main())
