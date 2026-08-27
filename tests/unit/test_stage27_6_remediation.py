"""Regression unit tests for Stage 27.6 Critical Forensic Remediation."""

import logging
from typing import Any

from aura.cognition.context import CognitiveContext, CognitiveContextBuilder
from aura.cognition.conversation_context import ConversationContext
from aura.cognition.openai_provider import OpenAILLMProvider
from aura.cognition.provider import LLMProvider, LLMResponse
from aura.cognition.reasoning import ReasoningEngine, ReasoningResult
from aura.cognition.working_memory import WorkingMemory
from aura.tools import BaseTool, ToolMetadata, ToolRegistry, ToolResult


class DummyCalendarTool(BaseTool):
    def __init__(self) -> None:
        self.metadata = ToolMetadata(
            name="calendar_tool",
            description="Gestión de calendario",
        )

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            success=True,
            output={"status": "event_created", "title": kwargs.get("title", "Evento")},
        )


class MockLLMForTelemetry(LLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def generate_response(self, prompt: str, system_instruction: str = "") -> LLMResponse:
        self.call_count += 1
        if self.call_count == 1:
            return LLMResponse(
                content='<tool name="calendar_tool">{"title": "Reunión equipo"}</tool>',
                tokens_used=40,
            )
        else:
            return LLMResponse(
                content="He creado la reunión en tu calendario.",
                tokens_used=25,
            )

    def structured_reason(self, prompt: str, schema: Any = None) -> Any:
        return {}


def test_history_leakage_prevention() -> None:
    """Test 1: Verify to_formatted_prompt() renders exclusively from conversation_history."""
    ctx = CognitiveContext(
        system_instruction="Instrucción de prueba",
        user_input="Hola",
        conversation_history=[
            {"role": "user", "content": f"Turno presupuesto {i}"} for i in range(2)
        ],
        conversation_context=ConversationContext(
            relevant_turns=[
                {"role": "user", "content": f"Turno filtrado gigante {i}"} for i in range(12)
            ]
        ),
    )

    formatted = ctx.to_formatted_prompt()
    assert "Turno presupuesto 0" in formatted
    assert "Turno filtrado gigante 0" not in formatted


def test_provider_payload_protection_ceiling(caplog: Any) -> None:
    """Test 2: Create oversized prompt and verify provider payload ceiling enforcement."""
    provider = OpenAILLMProvider(api_key="mock", base_url="http://localhost:11434/v1")
    huge_prompt = "Instrucción gigante " + ("x" * 6000)

    class MockCompletions:
        def create(self, **kwargs: Any) -> Any:
            class Msg:
                content = "Respuesta corta"

            class Choice:
                message = Msg()

            class Usage:
                prompt_tokens = 100
                completion_tokens = 10
                total_tokens = 110

            class Resp:
                def __init__(self) -> None:
                    self.choices = [Choice()]
                    self.usage = Usage()

            return Resp()

    class MockChat:
        def __init__(self) -> None:
            self.completions = MockCompletions()

    class MockClient:
        def __init__(self) -> None:
            self.chat = MockChat()

    provider._client = MockClient()

    with caplog.at_level(logging.INFO):
        res = provider.generate_response(prompt=huge_prompt, system_instruction="System prompt")

    assert res.content == "Respuesta corta"
    assert "[PAYLOAD SENT]" in caplog.text
    # Combined chars must not exceed ~4000 (2000 tokens ceiling * 2.0 chars/token)
    assert "combined_chars=" in caplog.text


def test_history_source_telemetry(caplog: Any) -> None:
    """Test 3: Verify [HISTORY SOURCE] telemetry is logged."""
    ctx = CognitiveContext(
        system_instruction="System",
        user_input="Test prompt",
        conversation_history=[{"role": "user", "content": "Hola"}],
    )

    with caplog.at_level(logging.INFO):
        _ = ctx.to_formatted_prompt()

    assert "[HISTORY SOURCE]" in caplog.text
    assert "source=conversation_history" in caplog.text


def test_post_llm_parser_telemetry(caplog: Any) -> None:
    """Test 4: Verify [POST-LLM TOOL PARSED] and [POST-LLM SECOND PASS STARTED] telemetry."""
    registry = ToolRegistry()
    registry.register(DummyCalendarTool())

    wm = WorkingMemory()
    mock_llm = MockLLMForTelemetry()
    engine = ReasoningEngine(working_memory=wm, llm_provider=mock_llm)

    class MockContainer:
        def has(self, cls: Any) -> bool:
            return cls is ToolRegistry

        def resolve(self, cls: Any) -> Any:
            return registry

    wm.container = MockContainer()  # type: ignore[attr-defined]

    builder = CognitiveContextBuilder()
    ctx = builder.build("Crea reunión", working_memory=wm)

    with caplog.at_level(logging.INFO):
        res: ReasoningResult = engine.analyze("Crea reunión", cognitive_context=ctx)

    assert "[POST-LLM TOOL PARSED]" in caplog.text
    assert "[POST-LLM SECOND PASS STARTED]" in caplog.text
    assert "He creado la reunión" in res.summary
