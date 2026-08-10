from __future__ import annotations

import os
import sys
from pathlib import Path

# Add src/ to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aura import AURA, AURABootOptions
from aura.cognition import CognitionModule
from aura.config import ConfigurationManager
from aura.memory import (
    EpisodicMemory,
    Fact,
    MemoryRetrievalEngine,
    Preference,
    SQLiteMemoryStore,
    SemanticMemory,
    UserPreferencesMemory,
)


def run_demo() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("\n========================================================")
    print(" 🧠 DEMO AURA 0.4.1 — RETRIEVAL SEMÁNTICO Y RANKING")
    print("========================================================\n")

    demo_db = "data/demo_retrieval.db"
    if os.path.exists(demo_db):
        try:
            os.remove(demo_db)
        except Exception:
            pass

    # ========================================================
    # 1. Crear base temporal y guardar hecho
    # ========================================================
    print("[PASO 1] Creando SQLiteMemoryStore e insertando hecho: (usuario -> cumpleaños -> 2 de agosto)...")
    store1 = SQLiteMemoryStore(db_path=demo_db)
    semantic1 = SemanticMemory(store=store1)
    semantic1.add_fact(
        Fact(
            subject="usuario",
            predicate="cumpleaños",
            object_val="2 de agosto",
            confidence=1.0,
            source="user",
        )
    )

    print("[PASO 2] Cerrando SQLiteMemoryStore (Limpiando memoria RAM)...")
    store1.close()

    # ========================================================
    # 2. Reabrir store desde SQLite
    # ========================================================
    print("\n[PASO 3] Reabriendo SQLiteMemoryStore desde cero...")
    store2 = SQLiteMemoryStore(db_path=demo_db)
    episodic2 = EpisodicMemory(store=store2)
    semantic2 = SemanticMemory(store=store2)
    prefs2 = UserPreferencesMemory(store=store2)

    retrieval_engine = MemoryRetrievalEngine(
        episodic=episodic2,
        semantic=semantic2,
        preferences=prefs2,
    )

    # ========================================================
    # 3. Probar las 4 formulaciones de consulta
    # ========================================================
    queries = [
        "¿Cuál es mi cumpleaños?",
        "¿Cuándo cumplo años?",
        "¿Recuerdas cuándo cumplo años?",
        "¿Qué día cumplo?",
        "Ahora, ¿recuerdas cuantos me cumplí años?",
    ]

    print("\n[PASO 4] Ejecutando consultas con variaciones léxicas en el RetrievalEngine:\n")

    for i, q in enumerate(queries, 1):
        print(f"  Consulta {i}: '{q}'")
        tokens = retrieval_engine._get_query_tokens(q)
        res = retrieval_engine.query(q)

        if res.facts:
            matched_fact = res.facts[0]
            score = retrieval_engine.score_fact(matched_fact, tokens)
            print(f"   -> FACT RECUPERADO: [{matched_fact.subject} -> {matched_fact.predicate}: {matched_fact.object_val}]")
            print(f"   -> SCORE DE RELEVANCIA: {score:.2f}")
        else:
            print("   -> (NINGÚN FACT RECUPERADO)")
        print("-" * 65)

    # ========================================================
    # 4. Probar la generación de Cognitive Context con AURA
    # ========================================================
    print("\n[PASO 5] Verificando inyección de memoria en CognitiveContext...")
    cfg = ConfigurationManager()
    cfg.set("memory.db_path", demo_db)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    cog = aura.container.resolve(CognitionModule)
    ctx = cog.context_builder.build("¿Cuándo cumplo años?")
    sys_prompt = ctx.to_system_prompt()

    print("\n--- [SYSTEM PROMPT ENVIADO AL LLM] ---")
    print(sys_prompt)
    print("--------------------------------------\n")

    aura.shutdown(wait=True)
    store2.close()

    if os.path.exists(demo_db):
        try:
            os.remove(demo_db)
        except Exception:
            pass

    print("========================================================")
    print(" [ÉXITO] DEMO AURA 0.4.1 COMPLETADA SATISFACTORIAMENTE")
    print("========================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
