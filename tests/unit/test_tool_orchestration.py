from __future__ import annotations

from typing import Any

from aura.cognition.intent import Intent, IntentType
from aura.cognition.tool_orchestrator import ToolOrchestrator
from aura.events import EventBus
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.builtins import CalculatorTool, DateTimeTool, SystemStatusTool
from aura.tools.registry import ToolRegistry


class HighRiskDestructiveTool(BaseTool):
    metadata = ToolMetadata(
        name="delete_all_files_tool",
        description="Destructive file deletion tool",
        category="system",
        risk_level="destructive",
        requires_confirmation=True,
        read_only=False,
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output="Files deleted")


def test_tool_orchestrator_datetime_selection() -> None:
    registry = ToolRegistry()
    registry.register(DateTimeTool())
    orchestrator = ToolOrchestrator()

    intent = Intent(intent_type=IntentType.QUESTION, confidence=0.9)
    results = orchestrator.orchestrate("¿Qué hora es?", intent, registry)

    assert len(results) == 1
    assert results[0]["tool_name"] == "datetime_tool"
    assert results[0]["success"] is True
    assert "datetime_formatted" in results[0]["output"]


def test_tool_orchestrator_calculator_selection() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    orchestrator = ToolOrchestrator()

    intent = Intent(intent_type=IntentType.QUESTION, confidence=0.9)
    results = orchestrator.orchestrate("¿Cuánto es 125 * 37?", intent, registry)

    assert len(results) == 1
    assert results[0]["tool_name"] == "calculator_tool"
    assert results[0]["success"] is True
    assert results[0]["output"] == 4625


def test_tool_orchestrator_system_status_selection() -> None:
    registry = ToolRegistry()
    registry.register(SystemStatusTool())
    orchestrator = ToolOrchestrator()

    intent = Intent(intent_type=IntentType.QUESTION, confidence=0.9)
    results = orchestrator.orchestrate("¿Cuál es el estado del sistema?", intent, registry)

    assert len(results) == 1
    assert results[0]["tool_name"] == "system_status_tool"
    assert results[0]["success"] is True
    assert results[0]["output"]["state"] == "Running"


def test_tool_orchestrator_max_tool_calls_limit() -> None:
    registry = ToolRegistry()
    registry.register(DateTimeTool())
    orchestrator = ToolOrchestrator(max_tool_calls_per_turn=0)

    intent = Intent(intent_type=IntentType.QUESTION, confidence=0.9)
    results = orchestrator.orchestrate("¿Qué hora es?", intent, registry)

    assert len(results) == 0


def test_tool_orchestrator_safety_destructive_tool_blocked() -> None:
    event_bus = EventBus()
    events_received: list[str] = []
    event_bus.subscribe(
        "ToolConfirmationRequired", lambda ev: events_received.append(ev.event_name())
    )

    registry = ToolRegistry()
    registry.register(HighRiskDestructiveTool())
    orchestrator = ToolOrchestrator(event_bus=event_bus)

    intent = Intent(intent_type=IntentType.COMMAND, confidence=0.9)

    # Force candidate call
    orchestrator._determine_tool_calls = lambda text, intent: [("delete_all_files_tool", {})]  # type: ignore[method-assign]

    results = orchestrator.orchestrate("Borra todos los archivos", intent, registry)

    assert len(results) == 1
    assert results[0]["success"] is False
    assert results[0]["requires_confirmation"] is True
    assert "ToolConfirmationRequired" in events_received
