from __future__ import annotations

from aura.cognition import CognitiveContext, CognitiveContextBuilder
from aura.cognition.working_memory import WorkingMemory
from aura.container import DependencyContainer


def test_cognitive_context_formatting() -> None:
    context = CognitiveContext(
        system_instruction="Eres AURA.",
        user_input="Hola AURA",
        conversation_history=[
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "¡Hola! ¿En qué te ayudo?"},
        ],
        world_entities=["Usuario (person)"],
        relevant_memories=["Nombre=Andres"],
        available_tools=[{"name": "weather", "description": "Get weather"}],
    )

    sys_prompt = context.to_system_prompt()
    formatted = context.to_formatted_prompt()

    assert "Eres AURA." in sys_prompt
    assert "weather" in sys_prompt
    assert "Usuario (person)" in sys_prompt
    assert "Nombre=Andres" in sys_prompt

    assert "[Usuario]: Hola" in formatted
    assert "[AURA]: ¡Hola! ¿En qué te ayudo?" in formatted
    assert "Usuario: Hola AURA" in formatted


def test_cognitive_context_builder() -> None:
    container = DependencyContainer()
    builder = CognitiveContextBuilder(container=container)

    wm = WorkingMemory()
    wm.add_conversation_turn("user", "Qué hora es?")
    wm.add_conversation_turn("assistant", "Son las 10 PM.")

    ctx = builder.build(
        input_text="Gracias",
        system_instruction="Identidad AURA",
        working_memory=wm,
    )

    assert ctx.system_instruction == "Identidad AURA"
    assert ctx.user_input == "Gracias"
    assert len(ctx.conversation_history) == 2
    assert ctx.conversation_history[0]["content"] == "Qué hora es?"
