from __future__ import annotations

from aura.audio.autonomous_agent import AutonomousVoiceAgent
from aura.cognition.intent import ControlIntentDetector, IntentDetector
from aura.container import DependencyContainer
from aura.memory import MemoryModule
from aura.memory.models import Fact, Preference
from aura.memory.store import SQLiteMemoryStore


def test_retrieval_trace():
    print("=== TRACING PHASE 1: Memory Retrieval for '¿Quién soy?' ===")
    store = SQLiteMemoryStore(db_path=":memory:")
    mem_module = MemoryModule(store=store)

    # Populate facts
    mem_module.semantic.add_fact(Fact(subject="usuario", predicate="nombre", object_val="Andrés", confidence=1.0, source="user"))
    mem_module.semantic.add_fact(Fact(subject="usuario", predicate="edad", object_val="26", confidence=1.0, source="user"))
    mem_module.semantic.add_fact(Fact(subject="usuario", predicate="ciudad", object_val="Medellín", confidence=1.0, source="user"))
    mem_module.semantic.add_fact(Fact(subject="usuario", predicate="actividad", object_val="estudiando ingeniería de software", confidence=1.0, source="user"))
    mem_module.semantic.add_fact(Fact(subject="usuario", predicate="ocupacion", object_val="desarrollador", confidence=1.0, source="user"))

    # Populate preference
    mem_module.preferences.set_preference("color_favorito", "rojo")

    # Perform query
    res = mem_module.retrieval.query("¿Quién soy?")
    print("Query '¿Quién soy?' results:")
    print("  Facts:")
    for f in res.facts:
        score = mem_module.retrieval.score_fact(f, mem_module.retrieval._get_query_tokens("¿Quién soy?"), is_open_recall=True)
        print(f"    - {f.predicate} = {f.object_val} (score={score:.2f}, conf={f.confidence})")
    
    print("  Preferences:")
    for p in res.preferences:
        score = mem_module.retrieval.score_preference(p, mem_module.retrieval._get_query_tokens("¿Quién soy?"), is_open_recall=True)
        print(f"    - {p.key} = {p.value} (score={score:.2f})")

    # Check FastPath decision in autonomous agent
    top_fact = res.facts[0] if res.facts else None
    top_pref = res.preferences[0] if res.preferences else None

    print("\nFastPath Selection Logic in AutonomousAgent:")
    if top_fact and top_fact.confidence >= 0.85:
        ans = f"Tu {top_fact.predicate} es {top_fact.object_val}."
        print(f"  Selected top_fact: '{ans}'")
    elif top_pref:
        ans = f"Tu preferencia para {top_pref.key} es {top_pref.value}."
        print(f"  Selected top_pref: '{ans}'")

    print("\n=== TRACING PHASE 2: Fast-Path for '¿Cuántos años tengo?' vs '¿Quién soy?' ===")
    q1 = "¿Quién soy?"
    q2 = "¿Cuántos años tengo?"

    is_fp1 = ControlIntentDetector.is_direct_memory_query(q1)
    is_fp2 = ControlIntentDetector.is_direct_memory_query(q2)

    print(f"Is '{q1}' direct memory query (FastPath)? {is_fp1}")
    print(f"Is '{q2}' direct memory query (FastPath)? {is_fp2}")


if __name__ == "__main__":
    test_retrieval_trace()
