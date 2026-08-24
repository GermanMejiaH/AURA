from __future__ import annotations

import json
from typing import Any

from aura.audio.autonomous_agent import AutonomousVoiceAgent
from aura.cognition.context import CognitiveContextBuilder, estimate_tokens, get_max_history_turns
from aura.cognition.intent import ControlIntentDetector, IntentDetector
from aura.cognition.module import CognitionModule
from aura.container import DependencyContainer
from aura.memory import MemoryModule
from aura.memory.models import Fact, Preference
from aura.memory.store import SQLiteMemoryStore


def test_defect1_occupation_retrieval() -> dict[str, Any]:
    print("=== DEFECT 1: OCCUPATION RETRIEVAL FAILURE ===")
    store = SQLiteMemoryStore(db_path=":memory:")
    mem_mod = MemoryModule(store=store)

    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="nombre", object_val="Andrés"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="edad", object_val="26"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="ciudad", object_val="Medellín"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="actividad", object_val="ingeniería de software"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="ocupación", object_val="desarrollador"))
    mem_mod.preferences.set_preference("color_favorito", "rojo")

    query_text = "¿Cuál es mi ocupación?"
    res = mem_mod.retrieval.query(query_text)

    facts = [(f.predicate, f.object_val) for f in res.facts]
    prefs = [(p.key, p.value) for p in res.preferences]

    top_fact = res.facts[0] if res.facts else None
    top_pref = res.preferences[0] if res.preferences else None

    print(f"Query: '{query_text}'")
    print(f"  Returned Facts: {facts}")
    print(f"  Returned Preferences: {prefs}")
    print(f"  Top Fact: {top_fact}")
    print(f"  Top Pref: {top_pref}")

    return {
        "query": query_text,
        "facts": facts,
        "preferences": prefs,
        "top_fact": str(top_fact),
        "top_pref": str(top_pref),
    }


def test_defect2_open_identity_recall() -> dict[str, Any]:
    print("\n=== DEFECT 2: OPEN IDENTITY RECALL FAILURE ===")
    store = SQLiteMemoryStore(db_path=":memory:")
    mem_mod = MemoryModule(store=store)

    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="nombre", object_val="Andrés"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="edad", object_val="26"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="ciudad", object_val="Medellín"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="actividad_principal", object_val="ingeniería de software"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="ocupacion_actual", object_val="desarrollador"))

    query_text = "¿Qué sabes de mí?"
    tokens = mem_mod.retrieval._get_query_tokens(query_text)
    is_open = mem_mod.retrieval._is_open_recall_query(query_text, tokens)

    res = mem_mod.retrieval.query(query_text)
    all_facts = mem_mod.semantic.all_facts()

    fact_dict = {f.predicate.lower().strip(): f.object_val for f in all_facts}
    for f in res.facts:
        fact_dict[f.predicate.lower().strip()] = f.object_val

    profile_parts = []
    if "nombre" in fact_dict:
        profile_parts.append(f"Nombre: {fact_dict['nombre']}")
    if "edad" in fact_dict:
        profile_parts.append(f"Edad: {fact_dict['edad']}")
    if "ciudad" in fact_dict:
        profile_parts.append(f"Ciudad: {fact_dict['ciudad']}")
    if "actividad" in fact_dict:
        profile_parts.append(f"Actividad: {fact_dict['actividad']}")
    if "ocupacion" in fact_dict:
        profile_parts.append(f"Ocupación: {fact_dict['ocupacion']}")

    print(f"Query: '{query_text}' | Is Open Recall: {is_open}")
    print(f"Fact Dict Keys: {list(fact_dict.keys())}")
    print(f"Profile Parts (Exact Key Check): {profile_parts}")

    return {
        "query": query_text,
        "is_open_recall": is_open,
        "fact_keys": list(fact_dict.keys()),
        "profile_parts": profile_parts,
    }


def test_defect3_stt_variants() -> dict[str, Any]:
    print("\n=== DEFECT 3: STT VARIANT FASTPATH FAILURE ===")
    stt_inputs = [
        "Don De Vivo",
        "don de vivo",
        "Donde vivo",
        "donde vivo",
        "Cuantos anos tengo",
        "cuantos anios tengo",
        "Que estudio",
        "Donde trabajo",
    ]

    results = []
    for inp in stt_inputs:
        is_fp = ControlIntentDetector.is_direct_memory_query(inp)
        norm = ControlIntentDetector.normalize_text(inp)
        results.append({"input": inp, "normalized": norm, "fastpath": is_fp})
        print(f"Input: '{inp}' -> Normalized: '{norm}' -> FastPath: {is_fp}")

    return {"stt_evals": results}


if __name__ == "__main__":
    d1 = test_defect1_occupation_retrieval()
    d2 = test_defect2_open_identity_recall()
    d3 = test_defect3_stt_variants()
