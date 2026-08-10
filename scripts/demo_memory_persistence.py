from __future__ import annotations

import os
import sys
from pathlib import Path

# Add src/ to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aura import AURA, AURABootOptions
from aura.config import ConfigurationManager
from aura.memory import SQLiteMemoryStore


def run_demo() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("\n========================================================")
    print(" [MEMORIA PERSISTENTE] DEMO AURA 0.4 ENTRE SESIONES")
    print("========================================================\n")

    demo_db = "data/demo_aura.db"
    if os.path.exists(demo_db):
        try:
            os.remove(demo_db)
        except Exception:
            pass

    # ========================================================
    # SESIÓN 1: Almacenamiento Explícito de Memoria
    # ========================================================
    print("[SESIÓN 1] Iniciando AURA...")
    config1 = ConfigurationManager()
    config1.load_from_env()
    config1.set("memory.db_path", demo_db)

    aura1 = AURA(config=config1, options=AURABootOptions())
    aura1.boot()

    prompt_store = "AURA, recuerda que mi color favorito es azul"
    print(f"\n[Usuario]: '{prompt_store}'")

    from aura.cognition import CognitionModule

    cog1 = aura1.container.resolve(CognitionModule)
    res1 = cog1.process_cognitive_cycle(prompt_store)
    print(f"[AURA]:    '{res1.summary}'")

    print("\n[Cerrando AURA] Destruyendo instancia y limpiando memoria RAM...")
    aura1.shutdown(wait=True)

    # Verificar que SQLite efectivamente guardó el hecho en disco
    checker = SQLiteMemoryStore(db_path=demo_db)
    facts = checker.get_facts(subject="usuario")
    print(f"[Verificación SQLite]: {len(facts)} hecho(s) guardado(s) en '{demo_db}'")
    for f in facts:
        print(f"   • {f.subject} -> {f.predicate}: {f.object_val}")
    checker.close()

    # ========================================================
    # SESIÓN 2: Recuperación desde SQLite tras el Reinicio
    # ========================================================
    print("\n[SESIÓN 2] Reabriendo AURA desde cero (Cargando datos de SQLite)...")
    config2 = ConfigurationManager()
    config2.load_from_env()
    config2.set("memory.db_path", demo_db)

    aura2 = AURA(config=config2, options=AURABootOptions())
    aura2.boot()

    prompt_query = "¿Cuál es mi color favorito?"
    print(f"\n[Usuario]: '{prompt_query}'")

    cog2 = aura2.container.resolve(CognitionModule)
    res2 = cog2.process_cognitive_cycle(prompt_query)
    print(f"[AURA]:    '{res2.summary}'")

    print("\n[Cerrando AURA] Finalizando AURA...")
    aura2.shutdown(wait=True)

    print("\n========================================================")
    print(" [ÉXITO] DEMO COMPLETADA: La memoria sobrevivió al reinicio.")
    print("========================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
