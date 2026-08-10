from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..events import (
    EventBus,
    ToolConfirmationRequired,
    ToolExecuted,
    ToolExecutionStarted,
    ToolFailed,
    ToolRequested,
)
from ..logging import get_logger
from ..tools.base import ToolResult

if TYPE_CHECKING:
    from ..tools.registry import ToolRegistry
    from .intent import Intent


class ToolOrchestrator:
    """Orchestrates tool selection, validation, safety check, and execution in cognition."""

    def __init__(
        self,
        max_tool_calls_per_turn: int = 3,
        event_bus: EventBus | None = None,
    ) -> None:
        self.max_tool_calls_per_turn = max_tool_calls_per_turn
        self.event_bus = event_bus

    def orchestrate(
        self,
        input_text: str,
        intent: Intent,
        registry: ToolRegistry | None,
    ) -> list[dict[str, Any]]:
        """Executes tool selection, safety check, and execution safely."""
        if registry is None:
            return []

        logger = get_logger("ToolOrchestrator")
        results: list[dict[str, Any]] = []

        # Determine tools to call (hybrid router)
        candidate_calls = self._determine_tool_calls(input_text, intent)
        if not candidate_calls:
            return []

        call_count = 0
        for tool_name, kwargs in candidate_calls:
            if call_count >= self.max_tool_calls_per_turn:
                logger.warning(
                    f"Reached max_tool_calls_per_turn ({self.max_tool_calls_per_turn}). "
                    f"Skipping remaining tool '{tool_name}'."
                )
                break

            tool = registry.get(tool_name)
            if tool is None:
                continue

            # Publish ToolRequested event
            if self.event_bus is not None:
                self.event_bus.publish(
                    ToolRequested(
                        source="ToolOrchestrator", tool_name=tool_name, raw_text=input_text
                    )
                )

            # Safety Check
            if tool.metadata.requires_confirmation or tool.metadata.risk_level == "destructive":
                logger.warning(
                    f"Tool '{tool_name}' requires confirmation "
                    f"(risk_level={tool.metadata.risk_level}). Execution blocked."
                )
                if self.event_bus is not None:
                    self.event_bus.publish(
                        ToolConfirmationRequired(
                            source="ToolOrchestrator",
                            tool_name=tool_name,
                            risk_level=tool.metadata.risk_level,
                            reason="Action requires explicit user confirmation",
                        )
                    )
                results.append(
                    {
                        "tool_name": tool_name,
                        "success": False,
                        "output": None,
                        "error": f"Herramienta '{tool_name}' requiere confirmación del usuario",
                        "requires_confirmation": True,
                    }
                )
                call_count += 1
                continue

            # Execute tool
            if self.event_bus is not None:
                self.event_bus.publish(
                    ToolExecutionStarted(source="ToolOrchestrator", tool_name=tool_name)
                )

            res: ToolResult = registry.execute(tool_name, **kwargs)
            call_count += 1

            if self.event_bus is not None:
                if res.success:
                    self.event_bus.publish(
                        ToolExecuted(
                            source="ToolOrchestrator",
                            tool_name=tool_name,
                            success=True,
                            execution_time_ms=res.execution_time_ms,
                        )
                    )
                else:
                    self.event_bus.publish(
                        ToolFailed(
                            source="ToolOrchestrator",
                            tool_name=tool_name,
                            error=res.error or "Unknown error",
                        )
                    )

            results.append(
                {
                    "tool_name": tool_name,
                    "success": res.success,
                    "output": res.output,
                    "error": res.error,
                    "execution_time_ms": res.execution_time_ms,
                }
            )

        return results

    def _determine_tool_calls(
        self, input_text: str, intent: Intent
    ) -> list[tuple[str, dict[str, Any]]]:
        """Hybrid deterministic router + intent router for tools."""
        text_clean = input_text.strip().lower()
        calls: list[tuple[str, dict[str, Any]]] = []

        # 1. DateTimeTool deterministic match
        dt_pat = r"\b(?:qu[eé]\s+hora|hora\s+es|qu[eé]\s+fecha|fecha\s+es|qu[eé]\s+d[ií]a)\b"
        if re.search(dt_pat, text_clean):
            if re.search(r"\b(?:fecha)\b", text_clean):
                calls.append(("datetime_tool", {"action": "date"}))
            elif re.search(r"\b(?:d[ií]a)\b", text_clean):
                calls.append(("datetime_tool", {"action": "day"}))
            else:
                calls.append(("datetime_tool", {"action": "now"}))
            return calls

        # 2. CalculatorTool deterministic match
        calc_pat = r"\b(?:calcula|cu[aá]nto\s+es|suma|resta|multiplica|divide)\b"
        if re.search(calc_pat, text_clean) or re.search(r"\d+\s*[\+\-\*\/\%]\s*\d+", text_clean):
            match = re.search(r"((?:\d+|\()[\d\s\+\-\*\/\%\(\)\.]+\d+)", text_clean)
            if match:
                expr = match.group(1).strip()
                calls.append(("calculator_tool", {"expression": expr}))
                return calls

        # 3. SystemStatusTool deterministic match
        sys_pat = (
            r"\b(?:estado\s+de\s+aura|estado\s+del\s+sistema|"
            r"salud\s+de\s+aura|m[oó]dulos\s+activos)\b"
        )
        if re.search(sys_pat, text_clean):
            calls.append(("system_status_tool", {}))
            return calls

        return calls
