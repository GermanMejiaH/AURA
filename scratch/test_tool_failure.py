from __future__ import annotations

import time
from typing import Any

from aura.cognition.intent import Intent
from aura.cognition.tool_orchestrator import ToolOrchestrator
from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.registry import ToolRegistry


class BrokenCrashTool(BaseTool):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(name="broken_tool", description="Always raises Exception")

    def execute(self, **kwargs: Any) -> ToolResult:
        raise RuntimeError("Network Timeout Exception Simulation")


class SlowHangTool(BaseTool):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(name="slow_tool", description="Hangs for a long time")

    def execute(self, **kwargs: Any) -> ToolResult:
        time.sleep(0.1)
        return ToolResult(success=True, output="Done slow work")


def test_tool_failure() -> dict[str, Any]:
    print("=== STAGE 26.4 AUDIT 4: TOOL FAILURE RESILIENCE ===")
    registry = ToolRegistry()
    registry.register(BrokenCrashTool())
    registry.register(SlowHangTool())

    orchestrator = ToolOrchestrator()

    # Direct execution test of crashing tool
    res_direct = registry.execute("broken_tool")
    direct_handled = (not res_direct.success and "Network Timeout Exception Simulation" in (res_direct.error or ""))

    # Orchestrator execution test
    # Mock intent and input that triggers broken_tool execution
    candidate_calls = [("broken_tool", {})]
    orchestrator._determine_tool_calls = lambda text, intent: candidate_calls  # type: ignore

    from aura.cognition.intent import IntentType
    mock_intent = Intent(intent_type=IntentType.COMMAND, confidence=1.0)
    orchestrated_results = orchestrator.orchestrate("ejecutar herramienta rota", mock_intent, registry)

    orchestrator_handled = (
        len(orchestrated_results) == 1
        and not orchestrated_results[0]["success"]
        and "Network Timeout Exception Simulation" in (orchestrated_results[0]["error"] or "")
    )

    passed = (direct_handled and orchestrator_handled)
    print(f"Direct Exception Caught: {direct_handled} | Orchestrator Handled: {orchestrator_handled} | Passed: {passed}")

    return {
        "direct_handled": direct_handled,
        "orchestrator_handled": orchestrator_handled,
        "error_msg": res_direct.error,
        "passed": passed,
    }


if __name__ == "__main__":
    test_tool_failure()
