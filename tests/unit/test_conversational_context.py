from __future__ import annotations

from aura.cognition import CognitiveContextBuilder, WorkingMemory
from aura.cognition.memory_detector import ExplicitMemoryDetector


def test_working_memory_sliding_window_truncation() -> None:
    wm = WorkingMemory(max_conversation_turns=12)

    # Add 16 turns (8 exchanges)
    for i in range(1, 9):
        wm.add_conversation_turn("user", f"Mensaje usuario {i}")
        wm.add_conversation_turn("assistant", f"Respuesta aura {i}")

    turns = wm.get_recent_conversation()
    assert len(turns) == 12

    # Oldest turns (user 1, assistant 1, user 2, assistant 2) must be truncated
    assert turns[0]["content"] == "Mensaje usuario 3"
    assert turns[1]["content"] == "Respuesta aura 3"
    assert turns[-2]["content"] == "Mensaje usuario 8"
    assert turns[-1]["content"] == "Respuesta aura 8"


def test_cognitive_context_builder_formats_12_turns() -> None:
    wm = WorkingMemory(max_conversation_turns=12)
    for i in range(1, 7):
        wm.add_conversation_turn("user", f"Pregunta {i}")
        wm.add_conversation_turn("assistant", f"Respuesta {i}")

    builder = CognitiveContextBuilder()
    ctx = builder.build(input_text="¿Puedes resumir?", working_memory=wm)

    formatted = ctx.to_formatted_prompt()
    assert "Historial conversacional reciente:" in formatted
    assert "[Usuario]: Pregunta 1" in formatted
    assert "[AURA]: Respuesta 6" in formatted
    assert "Usuario: ¿Puedes resumir?" in formatted


def test_casual_banter_does_not_trigger_explicit_memory() -> None:
    banter_samples = [
        "Hola AURA",
        "¿Cómo estás?",
        "Qué bonito día hace hoy",
        "Gracias por tu ayuda",
        "Hasta luego",
    ]
    for text in banter_samples:
        directive = ExplicitMemoryDetector.detect(text)
        assert directive.detected is False


def test_fresh_working_memory_starts_empty() -> None:
    wm1 = WorkingMemory()
    wm1.add_conversation_turn("user", "Hola")
    assert len(wm1.get_recent_conversation()) == 1

    wm2 = WorkingMemory()
    assert len(wm2.get_recent_conversation()) == 0
