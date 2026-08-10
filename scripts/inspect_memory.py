from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add src/ to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aura.memory import SQLiteMemoryStore


def inspect_db(db_path: str) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not os.path.exists(db_path):
        print(f"[inspect_memory] La base de datos '{db_path}' no existe.")
        return

    print("========================================================")
    print(f" 🔍 INSPECCIÓN DE MEMORIA PERSISTENTE AURA: {db_path}")
    print("========================================================\n")

    store = SQLiteMemoryStore(db_path=db_path)

    # 1. FACTS
    facts = store.get_facts()
    print(f"📌 [FACTS / HECHOS]: {len(facts)} en total")
    print("-" * 75)
    if facts:
        for f in facts:
            created_str = f.created_at.isoformat() if hasattr(f.created_at, "isoformat") else str(f.created_at)
            print(f"ID:          {f.id}")
            print(f"Sujeto:      {f.subject}")
            print(f"Predicado:   {f.predicate}")
            print(f"Objeto:      {f.object_val}")
            print(f"Confianza:   {f.confidence}")
            print(f"Fuente:      {f.source}")
            print(f"Creado:      {created_str}")
            print("-" * 75)
    else:
        print("  (Sin hechos registrados)\n")

    # 2. PREFERENCES
    prefs = store.get_all_preferences()
    print(f"\n⚙️ [PREFERENCES / PREFERENCIAS]: {len(prefs)} en total")
    print("-" * 75)
    if prefs:
        for p in prefs:
            updated_str = p.updated_at.isoformat() if hasattr(p.updated_at, "isoformat") else str(p.updated_at)
            print(f"Clave:      {p.key}")
            print(f"Valor:      {p.value}")
            print(f"Categoría:  {p.category}")
            print(f"Actualizado:{updated_str}")
            print("-" * 75)
    else:
        print("  (Sin preferencias registradas)\n")

    # 3. EPISODES
    episodes = store.get_episodes()
    print(f"\n📖 [EPISODES / EPISODIOS]: {len(episodes)} en total")
    print("-" * 75)
    if episodes:
        for ep in episodes:
            ts_str = ep.timestamp.isoformat() if hasattr(ep.timestamp, "isoformat") else str(ep.timestamp)
            print(f"ID:          {ep.id}")
            print(f"Resumen:     {ep.summary}")
            print(f"Detalles:    {ep.details}")
            print(f"Etiquetas:   {ep.tags}")
            print(f"Importancia: {ep.importance}")
            print(f"Timestamp:   {ts_str}")
            print("-" * 75)
    else:
        print("  (Sin episodios registrados)\n")

    store.close()
    print("========================================================\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspecciona el contenido de data/aura.db")
    parser.add_argument("--db", type=str, default="data/aura.db", help="Ruta al archivo .db de SQLite")
    args = parser.parse_args()
    inspect_db(args.db)


if __name__ == "__main__":
    main()
