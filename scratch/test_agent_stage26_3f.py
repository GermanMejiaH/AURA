from __future__ import annotations

import json
from aura.audio.autonomous_agent import AutonomousVoiceAgent
from aura.container import DependencyContainer
from aura.memory import MemoryModule
from aura.memory.models import Fact
from aura.memory.store import SQLiteMemoryStore


def test_agent_fastpath_queries() -> None:
    store = SQLiteMemoryStore(db_path=":memory:")
    mem_mod = MemoryModule(store=store)

    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="nombre", object_val="Andrés"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="edad", object_val="26"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="ciudad", object_val="Medellín"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="actividad_principal", object_val="ingeniería de software"))
    mem_mod.semantic.add_fact(Fact(subject="usuario", predicate="ocupacion_actual", object_val="desarrollador"))
    mem_mod.preferences.set_preference("color_favorito", "rojo")

    container = DependencyContainer()
    container.register(MemoryModule, instance=mem_mod)

    mock_llm = type("LLMMock", (), {})()
    agent = AutonomousVoiceAgent(llm_provider=mock_llm)
    cognition_mock = type("CogMock", (), {"_container": container})()
    agent.cognition = cognition_mock

    test_cases = [
        "¿Cuál es mi ocupación?",
        "¿Qué sabes de mí?",
        "¿Quién soy?",
        "Don De Vivo",
        "cuantos anios tengo",
        "¿Qué estudié?",
    ]

    for q in test_cases:
        print(f"\n--- Testing Query: '{q}' ---")
        res_retrieval = mem_mod.retrieval.query(q)
        is_open_query = mem_mod.retrieval._is_open_recall_query(
            q, mem_mod.retrieval._get_query_tokens(q)
        )

        from aura.memory.retrieval import normalize_text

        all_facts = list(mem_mod.semantic.all_facts()) + list(res_retrieval.facts)
        fact_dict: dict[str, str] = {}
        for f in all_facts:
            norm_p = normalize_text(f.predicate)
            fact_dict[norm_p] = f.object_val

        profile_parts: list[str] = []
        name_val = next((v for k, v in fact_dict.items() if "nombre" in k or k == "usuario"), None)
        if name_val:
            profile_parts.append(f"Nombre: {name_val}")
        age_val = next((v for k, v in fact_dict.items() if "edad" in k or "anos" in k or "anios" in k), None)
        if age_val:
            profile_parts.append(f"Edad: {age_val}")
        city_val = next((v for k, v in fact_dict.items() if "ciudad" in k or "vivo" in k or "residencia" in k or "ubicacion" in k), None)
        if city_val:
            profile_parts.append(f"Ciudad: {city_val}")
        act_val = next((v for k, v in fact_dict.items() if "actividad" in k or "estudio" in k or "carrera" in k), None)
        if act_val:
            profile_parts.append(f"Actividad: {act_val}")
        occ_val = next((v for k, v in fact_dict.items() if "ocupacion" in k or "trabajo" in k or "profesion" in k or "empleo" in k), None)
        if occ_val:
            profile_parts.append(f"Ocupación: {occ_val}")

        top_fact = res_retrieval.facts[0] if res_retrieval.facts else None
        top_pref = res_retrieval.preferences[0] if res_retrieval.preferences else None

        ans = ""
        if is_open_query and profile_parts:
            ans = "Perfil de usuario: " + " | ".join(profile_parts) + "."
        elif top_fact and top_fact.confidence >= 0.50:
            norm_pred = normalize_text(top_fact.predicate)
            val = top_fact.object_val
            if "edad" in norm_pred or "anos" in norm_pred:
                ans = f"Tienes {val} años."
            elif "ciudad" in norm_pred or "vivo" in norm_pred:
                ans = f"Vives en {val}."
            elif "nombre" in norm_pred:
                ans = f"Tu nombre es {val}."
            elif "ocupacion" in norm_pred or "trabajo" in norm_pred or "profesion" in norm_pred or "empleo" in norm_pred:
                ans = f"Trabajas como {val}."
            elif "actividad" in norm_pred or "estudio" in norm_pred or "carrera" in norm_pred:
                ans = f"Tu actividad es {val}."
            else:
                ans = f"Tu {top_fact.predicate} es {val}."
        elif top_pref:
            ans = f"Tu preferencia para {top_pref.key} es {top_pref.value}."

        print(f"FastPath Response: '{ans}'")


if __name__ == "__main__":
    test_agent_fastpath_queries()
