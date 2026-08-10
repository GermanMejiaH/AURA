from __future__ import annotations

from aura.cognition.context import CognitiveContext


def test_cognitive_context_with_tool_results() -> None:
    ctx = CognitiveContext(
        system_instruction="System instruction",
        user_input="¿Qué hora es?",
        tool_results=[
            {
                "tool_name": "datetime_tool",
                "success": True,
                "output": "Monday, August 10, 2026 03:25:00",
                "execution_time_ms": 0.5,
            }
        ],
    )

    sys_prompt = ctx.to_system_prompt()
    assert "[RESULTADOS DE HERRAMIENTAS RECIENTES]" in sys_prompt
    assert "Herramienta 'datetime_tool': Monday, August 10, 2026 03:25:00" in sys_prompt
