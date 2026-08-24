from __future__ import annotations

import json
import time
from typing import Any

from aura.cognition.context import CognitiveContextBuilder, get_max_history_turns
from aura.cognition.intent import IntentDetector
from aura.cognition.memory_detector import ExplicitMemoryDetector
from aura.container import DependencyContainer
from aura.memory import MemoryModule
from aura.memory.models import Fact
from aura.memory.store import SQLiteMemoryStore
from aura.telemetry import TelemetryManager


def run_phase1_and_phase2() -> dict[str, Any]:
    print("=== PHASE 1 & PHASE 2: MEMORY EXTRACTION & RETRIEVAL VALIDATION ===")
    store = SQLiteMemoryStore(db_path=":memory:")
    mem_module = MemoryModule(store=store)

    statements = [
        ("Soy Andrés.", "nombre", "Andrés"),
        ("Tengo 26 años.", "edad", "26"),
        ("Vivo en Medellín.", "ciudad", "Medellín"),
        ("Estudio ingeniería de software.", "actividad", "estudiando ingeniería de software"),
        ("Trabajo como desarrollador.", "ocupacion", "desarrollador"),
    ]

    extraction_results = []
    for stmt, expected_pred, expected_val in statements:
        directive = ExplicitMemoryDetector.detect(stmt)
        detected = directive.detected
        pred = directive.predicate
        val = directive.object_val

        # Add to memory
        if detected:
            mem_module.semantic.add_fact(
                Fact(
                    subject=directive.subject,
                    predicate=directive.predicate,
                    object_val=directive.object_val,
                    source="user",
                )
            )

        # Query SQLite directly
        db_facts = store.get_facts(subject="usuario", predicate=expected_pred)
        persisted = len(db_facts) > 0 and db_facts[0].object_val == expected_val

        extraction_results.append({
            "statement": stmt,
            "detected": detected,
            "predicate": pred,
            "object_val": val,
            "persisted": persisted,
        })
        print(f"Statement: '{stmt}' | Detected={detected} | Predicate='{pred}' | Value='{val}' | Persisted={persisted}")

    # Phase 2: Memory Retrieval
    queries = [
        "¿Qué recuerdas de mí?",
        "¿Quién soy?",
        "¿Cuántos años tengo?",
        "¿Dónde vivo?",
        "¿Qué estudio?",
    ]

    retrieval_results = []
    for q in queries:
        res = mem_module.retrieval.query(q)
        facts_str = [f"{f.predicate}={f.object_val}" for f in res.facts]
        retrieval_results.append({
            "query": q,
            "facts_count": len(res.facts),
            "facts": facts_str,
        })
        print(f"Query: '{q}' | Returned {len(res.facts)} facts: {facts_str}")

    return {"extractions": extraction_results, "retrievals": retrieval_results}


def run_phase3_token_consumption() -> dict[str, Any]:
    print("\n=== PHASE 3: TOKEN CONSUMPTION VALIDATION ===")
    container = DependencyContainer()
    store = SQLiteMemoryStore(db_path=":memory:")
    mem_module = MemoryModule(store=store)
    container.register(SQLiteMemoryStore, instance=store)
    container.register(MemoryModule, instance=mem_module)

    builder = CognitiveContextBuilder(container=container)

    casual_prompts = [
        "hola", "buenos días", "buenas noches", "saludos", "gracias",
        "de nada", "cómo estás", "como estas", "hey", "hola aura",
        "buenas tardes", "hi", "hello", "hasta luego", "nos vemos",
        "adiós", "bye", "chao", "un gusto", "excelente"
    ]

    factual_prompts = [
        "¿qué hora es?", "¿dónde está la cocina?", "¿cuál es la fecha de hoy?",
        "¿qué tiempo hace?", "¿dónde está la oficina?", "¿qué es python?",
        "¿quién escribió el código?", "¿cuál es el estado del sistema?",
        "¿dónde queda Medellín?", "¿cuál es la capital de Colombia?",
        "¿qué es AURA?", "¿cuál es el modelo de lenguaje?",
        "¿qué sensores están activos?", "¿dónde está el altavoz?",
        "¿cuántos módulos hay?", "¿cuál es el nivel de batería?",
        "¿qué tareas hay?", "¿dónde está la pantalla?",
        "¿qué versión es esta?", "¿dónde queda el laboratorio?"
    ]

    memory_prompts = [
        "¿qué recuerdas de mí?", "¿quién soy?", "¿cuántos años tengo?",
        "¿dónde vivo?", "¿qué estudio?", "recuerdas mi nombre",
        "qué sabes sobre mí", "cuál es mi ocupación", "cuál es mi ciudad",
        "dime mis datos personales", "qué información guardaste",
        "cuál es mi edad", "dónde trabajo", "qué carrera estudio",
        "cuál es mi profesión", "qué recuerdas de mis gustos",
        "quién es Andrés", "cuántos años dije que tenía",
        "qué recuerdas del pasado", "dime mi perfil de usuario"
    ]

    planning_prompts = [
        "crea un plan para organizar el sistema", "organiza la agenda del día",
        "programa una reunión para mañana", "planifica la navegación a la cocina",
        "crea una tarea de supervisión", "organiza los archivos del proyecto",
        "prepara una rutina de mantenimiento", "diseña un plan de pruebas",
        "establece las prioridades de la semana", "crea un objetivo de observabilidad",
        "organiza el entorno de trabajo", "planifica el respaldo de la base de datos",
        "crea una estrategia de optimización", "programa el apagado de sensores",
        "organiza los eventos del calendario", "prepara el informe de métricas",
        "diseña un plan de contingencia", "establece metas de autonomía",
        "crea una lista de tareas pendientes", "planifica la auditoría de código"
    ]

    categories = {
        "casual": (casual_prompts, 500),
        "factual": (factual_prompts, 700),
        "memory": (memory_prompts, 1200),
        "planning": (planning_prompts, 1500),
    }

    stats: dict[str, Any] = {}
    worst_case = {"prompt": "", "tokens": 0, "category": ""}

    for cat_name, (prompt_list, limit) in categories.items():
        tokens_list = []
        history_turns_list = []
        memory_tokens_list = []
        episode_tokens_list = []
        goal_tokens_list = []
        tool_tokens_list = []

        for p in prompt_list:
            ctx = builder.build(input_text=p)
            sys_p = ctx.to_system_prompt()
            fmt_p = ctx.to_formatted_prompt()
            tot_tok = len(sys_p + fmt_p) // 4

            tokens_list.append(tot_tok)
            h_source = ctx.conversation_history
            max_h = get_max_history_turns(ctx.intent, p)
            h_turns = len(h_source[-max_h:]) if h_source else 0
            history_turns_list.append(h_turns)

            mem_tok = len(" ".join(ctx.relevant_memories)) // 4
            ep_tok = len(" ".join(getattr(e, "summary", "") for e in ctx.relevant_episodes)) // 4
            goal_tok = len(" ".join(getattr(g.goal, "description", "") for g in ctx.prioritized_goals)) // 4
            tool_tok = len(" ".join(t.get("name", "") + " " + t.get("description", "") for t in ctx.available_tools)) // 4

            memory_tokens_list.append(mem_tok)
            episode_tokens_list.append(ep_tok)
            goal_tokens_list.append(goal_tok)
            tool_tokens_list.append(tool_tok)

            if tot_tok > worst_case["tokens"]:
                worst_case = {"prompt": p, "tokens": tot_tok, "category": cat_name}

        avg_tot = sum(tokens_list) / len(tokens_list)
        avg_h_turns = sum(history_turns_list) / len(history_turns_list)
        avg_mem_tok = sum(memory_tokens_list) / len(memory_tokens_list)
        avg_ep_tok = sum(episode_tokens_list) / len(episode_tokens_list)
        avg_goal_tok = sum(goal_tokens_list) / len(goal_tokens_list)
        avg_tool_tok = sum(tool_tokens_list) / len(tool_tokens_list)

        passed = max(tokens_list) < limit

        stats[cat_name] = {
            "avg_prompt_tokens": round(avg_tot, 1),
            "max_prompt_tokens": max(tokens_list),
            "avg_history_turns": round(avg_h_turns, 1),
            "avg_memory_tokens": round(avg_mem_tok, 1),
            "avg_episode_tokens": round(avg_ep_tok, 1),
            "avg_goal_tokens": round(avg_goal_tok, 1),
            "avg_tool_tokens": round(avg_tool_tok, 1),
            "limit": limit,
            "passed": passed,
        }
        print(f"Category '{cat_name}': Avg Tokens={avg_tot:.1f} | Max Tokens={max(tokens_list)} | Limit={limit} | Passed={passed}")

    print(f"Worst Case Prompt: '{worst_case['prompt']}' ({worst_case['tokens']} tokens in '{worst_case['category']}')")
    return {"stats": stats, "worst_case": worst_case}


def run_phase4_long_conversation() -> dict[str, Any]:
    print("\n=== PHASE 4: WORKING MEMORY VALIDATION (50+ TURNS) ===")
    store = SQLiteMemoryStore(db_path=":memory:")
    container = DependencyContainer()
    container.register(SQLiteMemoryStore, instance=store)

    history = []
    for i in range(1, 53):
        history.append({"role": "user", "content": f"Turno usuario número {i} de la conversación larga."})
        history.append({"role": "assistant", "content": f"Respuesta de AURA para el turno {i} de la sesión."})

    builder = CognitiveContextBuilder(container=container)
    dummy_wm = type("WM", (), {"get_recent_conversation": lambda *args, **kwargs: history})()
    ctx = builder.build(
        input_text="¿Cómo va nuestra conversación?",
        working_memory=dummy_wm,
    )

    fmt_p = ctx.to_formatted_prompt()
    lines = [line.strip() for line in fmt_p.splitlines() if line.strip().startswith("[")]

    rendered_turns_count = len(lines)
    full_persisted_turns = len(history)

    print(f"Full Persisted Turns: {full_persisted_turns} | Rendered Turns in Voice Prompt: {rendered_turns_count}")
    print(f"Adaptive Cap Obeyed (<= 4 turns): {rendered_turns_count <= 4}")

    return {
        "full_persisted_turns": full_persisted_turns,
        "rendered_turns_count": rendered_turns_count,
        "passed": rendered_turns_count <= 4 and full_persisted_turns == 104,
    }


def run_phase5_voice_cycle_simulation() -> dict[str, Any]:
    print("\n=== PHASE 5: VOICE CYCLE SIMULATION (15 MINUTES / INTERVALS) ===")
    container = DependencyContainer()
    store = SQLiteMemoryStore(db_path=":memory:")
    mem_module = MemoryModule(store=store)
    container.register(SQLiteMemoryStore, instance=store)
    container.register(MemoryModule, instance=mem_module)

    builder = CognitiveContextBuilder(container=container)
    telemetry = TelemetryManager.get_instance()

    snapshots = []
    turns_history = []

    for minute in range(1, 16):
        t0 = time.perf_counter()
        # Simulate voice turn
        user_msg = f"Mensaje de voz minuto {minute}: comprobación de estado"
        turns_history.append({"role": "user", "content": user_msg})

        dummy_wm_v = type("WM", (), {"get_recent_conversation": lambda *args, **kwargs: list(turns_history)})()
        ctx = builder.build(input_text=user_msg, working_memory=dummy_wm_v)
        sys_p = ctx.to_system_prompt()
        fmt_p = ctx.to_formatted_prompt()
        tot_tok = len(sys_p + fmt_p) // 4

        asst_msg = f"Entendido minuto {minute}, todo estable."
        turns_history.append({"role": "assistant", "content": asst_msg})

        latency_ms = (time.perf_counter() - t0) * 1000
        telemetry.record_token_usage(prompt_tokens=tot_tok, completion_tokens=20)

        snapshots.append({
            "minute": minute,
            "prompt_tokens": tot_tok,
            "completion_tokens": 20,
            "latency_ms": round(latency_ms, 2),
            "rendered_history_turns": len([l for l in fmt_p.splitlines() if l.strip().startswith("[")]),
        })

    print(f"Simulated 15 voice cycle intervals cleanly. Max prompt tokens observed: {max(s['prompt_tokens'] for s in snapshots)}")
    return {"snapshots": snapshots}


if __name__ == "__main__":
    p1_p2 = run_phase1_and_phase2()
    p3 = run_phase3_token_consumption()
    p4 = run_phase4_long_conversation()
    p5 = run_phase5_voice_cycle_simulation()

    full_report_data = {
        "phase1_phase2": p1_p2,
        "phase3": p3,
        "phase4": p4,
        "phase5": p5,
    }

    with open("scratch/stage26_3b_validation_results.json", "w", encoding="utf-8") as f:
        json.dump(full_report_data, f, indent=2, ensure_ascii=False)

    print("\nValidation data saved to scratch/stage26_3b_validation_results.json")
