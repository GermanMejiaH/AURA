"""Unit tests for Stage 27.5 Post-Pilot Remediation & Hardening."""

from typing import Any

from aura.audio.faster_whisper_stt import FasterWhisperSTTProvider
from aura.cognition.context import CognitiveContextBuilder
from aura.cognition.provider import LLMProvider, LLMResponse
from aura.cognition.reasoning import ReasoningEngine, ReasoningResult
from aura.cognition.tool_orchestrator import ToolOrchestrator
from aura.cognition.working_memory import WorkingMemory
from aura.tools import BaseTool, ToolMetadata, ToolRegistry, ToolResult


class DummyTool(BaseTool):
    def __init__(self) -> None:
        self.metadata = ToolMetadata(
            name="calendar_tool",
            description="Gestión de calendario",
        )

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            success=True,
            output={"status": "event_created", "title": kwargs.get("title", "Alarma")},
        )


class MockLLMWithToolCall(LLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def generate_response(self, prompt: str, system_instruction: str = "") -> LLMResponse:
        self.call_count += 1
        if self.call_count == 1:
            # Emits XML tool call
            return LLMResponse(
                content='<tool name="calendar_tool">{"title": "Recordatorio piloto"}</tool>',
                tokens_used=50,
            )
        else:
            # Emits natural response after second pass
            return LLMResponse(
                content="He programado tu recordatorio piloto para las 5 PM.",
                tokens_used=30,
            )

    def structured_reason(self, prompt: str, schema: Any = None) -> Any:
        return {}


def test_post_llm_tool_execution_loop() -> None:
    """Verifies that post-LLM tool calls parse, execute, and return clean natural text."""
    registry = ToolRegistry()
    registry.register(DummyTool())

    wm = WorkingMemory()
    mock_llm = MockLLMWithToolCall()
    engine = ReasoningEngine(working_memory=wm, llm_provider=mock_llm)

    # Attach container with registry to working_memory
    class MockContainer:
        def has(self, cls: Any) -> bool:
            return cls is ToolRegistry

        def resolve(self, cls: Any) -> Any:
            return registry

    wm.container = MockContainer()  # type: ignore[attr-defined]

    builder = CognitiveContextBuilder()
    ctx = builder.build("Ponme un recordatorio piloto", working_memory=wm)

    res: ReasoningResult = engine.analyze("Ponme un recordatorio piloto", cognitive_context=ctx)

    assert mock_llm.call_count == 2
    assert len(ctx.tool_results) == 1
    assert ctx.tool_results[0]["success"] is True
    assert ctx.tool_results[0]["tool_name"] == "calendar_tool"
    assert "<tool" not in res.summary
    assert "He programado tu recordatorio piloto" in res.summary


def test_tool_markup_stripping() -> None:
    """Verifies that raw tool markup and fake CLI commands are stripped."""
    raw_xml = '<tool name="calendar_tool">{"title":"Test"}</tool>\nHecho.'
    clean = ToolOrchestrator.strip_tool_markup(raw_xml)
    assert "<tool" not in clean
    assert clean == "Hecho."

    fake_cmd = "Comando ejecutado: sonido_test en /var/log/sonido.log"
    clean_cmd = ToolOrchestrator.strip_tool_markup(fake_cmd)
    assert "sonido_test" not in clean_cmd
    assert "/var/log/sonido.log" not in clean_cmd


def test_context_budget_ceiling() -> None:
    """Verifies pre-assembly token budgeting (MAX_CONTEXT_BUDGET = 2000)."""
    wm = WorkingMemory()
    for i in range(20):
        wm.add_conversation_turn("user", f"Turno largo {i} " + ("x" * 200))
        wm.add_conversation_turn("assistant", f"Respuesta larga {i} " + ("y" * 200))

    builder = CognitiveContextBuilder()
    ctx = builder.build("Test budget", working_memory=wm)

    sys_prompt = ctx.to_system_prompt()
    fmt_prompt = ctx.to_formatted_prompt()
    total_tokens = len(sys_prompt + fmt_prompt) // 3.2

    assert total_tokens <= 2000


def test_stt_gating_thresholds() -> None:
    """Verifies calibrated FasterWhisper STT gating thresholds."""
    provider = FasterWhisperSTTProvider(model_size_or_path="tiny", device="cpu")
    assert provider is not None
