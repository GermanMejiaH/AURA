from __future__ import annotations

from aura.cognition.context import CognitiveContext, CognitiveContextBuilder, get_max_history_turns
from aura.cognition.memory_detector import ExplicitMemoryDetector
from aura.container import DependencyContainer
from aura.memory.module import MemoryModule
from aura.memory.store import SQLiteMemoryStore


def test_explicit_memory_detector_natural_declarations() -> None:
    """Verify natural Spanish memory declarations produce correct predicates and values."""
    # 1. Age
    d_age = ExplicitMemoryDetector.detect("Tengo 26 años")
    assert d_age.detected is True
    assert d_age.predicate == "edad"
    assert d_age.object_val == "26"

    # 2. Location
    d_loc = ExplicitMemoryDetector.detect("Vivo en Medellín")
    assert d_loc.detected is True
    assert d_loc.predicate == "ciudad"
    assert d_loc.object_val == "Medellín"

    # 3. Studies
    d_study = ExplicitMemoryDetector.detect("Estudio ingeniería de software")
    assert d_study.detected is True
    assert d_study.predicate == "actividad"
    assert "ingeniería de software" in d_study.object_val

    # 4. Occupation
    d_job = ExplicitMemoryDetector.detect("Trabajo como desarrollador")
    assert d_job.detected is True
    assert d_job.predicate == "ocupacion"
    assert d_job.object_val == "desarrollador"

    # 5. Employer
    d_emp = ExplicitMemoryDetector.detect("Trabajo en Empresa X")
    assert d_emp.detected is True
    assert d_emp.predicate == "empleador"
    assert d_emp.object_val == "Empresa X"

    # 6. Name
    d_name = ExplicitMemoryDetector.detect("Soy Andrés")
    assert d_name.detected is True
    assert d_name.predicate == "nombre"
    assert d_name.object_val == "Andrés"


def test_explicit_memory_end_to_end_persistence() -> None:
    """Verify natural declarations reach SemanticMemory.add_fact() and persist to SQLite."""
    store = SQLiteMemoryStore(db_path=":memory:")
    mem_module = MemoryModule(store=store)

    # Simulate "Tengo 26 años"
    directive = ExplicitMemoryDetector.detect("Tengo 26 años")
    assert directive.detected is True

    from aura.memory.models import Fact

    mem_module.semantic.add_fact(
        Fact(
            subject=directive.subject,
            predicate=directive.predicate,
            object_val=directive.object_val,
            source="user",
        )
    )

    facts = store.get_facts(subject="usuario", predicate="edad")
    assert len(facts) == 1
    assert facts[0].object_val == "26"


def test_working_memory_history_window_capping() -> None:
    """Verify hydrated history of 12 turns renders <= 4 turns in formatted voice prompt."""
    history = [
        {"role": "user", "content": f"Turno usuario {i}"}
        if i % 2 == 0
        else {"role": "assistant", "content": f"Turno AURA {i}"}
        for i in range(12)
    ]

    ctx = CognitiveContext(
        system_instruction="Instrucción de prueba",
        user_input="Tengo 26 años",
        conversation_history=history,
    )

    formatted_prompt = ctx.to_formatted_prompt()

    # Calculate rendered turns count
    rendered_lines = [
        line for line in formatted_prompt.splitlines() if line.strip().startswith("[")
    ]
    assert len(rendered_lines) <= 4

    # Verify oldest turns (e.g. Turno 0) are excluded, newest turns (e.g. Turno 11) are included
    assert "Turno usuario 0" not in formatted_prompt
    assert "Turno AURA 11" in formatted_prompt


def test_adaptive_history_scaling_policy() -> None:
    """Verify max history turns for different intents."""
    # Greeting -> 1 turn
    assert get_max_history_turns(None, "hola") == 1

    # Factual Question -> 2 turns
    assert get_max_history_turns("QUESTION", "dónde está la oficina") == 2

    # Natural Conversation -> 4 turns
    assert get_max_history_turns(None, "tengo 26 años") == 4

    # Planning / Task -> 6 turns
    assert get_max_history_turns("TASK_REQUEST", "crea un plan") == 6

    # Complex Recall / Reflection -> 8 turns
    assert get_max_history_turns("MEMORY_QUERY", "qué recuerdas de mí") == 8


def test_production_prompt_size_under_1000_tokens() -> None:
    """Verify prompt size for simple declarations stays under 1000 tokens."""
    container = DependencyContainer()
    store = SQLiteMemoryStore(db_path=":memory:")
    mem_module = MemoryModule(store=store)
    container.register(SQLiteMemoryStore, instance=store)
    container.register(MemoryModule, instance=mem_module)

    builder = CognitiveContextBuilder(container=container)
    ctx = builder.build(input_text="Tengo 26 años")

    sys_prompt = ctx.to_system_prompt()
    fmt_prompt = ctx.to_formatted_prompt()
    total_tokens = len(sys_prompt + fmt_prompt) // 4

    assert total_tokens < 1000
