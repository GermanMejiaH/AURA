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

        # Determine tools to call (hybrid router)
        candidate_calls = self._determine_tool_calls(input_text, intent)
        if not candidate_calls:
            return []

        return self.execute_parsed_tools(candidate_calls, registry)

    def execute_parsed_tools(
        self,
        candidate_calls: list[tuple[str, dict[str, Any]]],
        registry: ToolRegistry | None,
        input_text: str = "",
    ) -> list[dict[str, Any]]:
        """Executes candidate tool calls against registry safely with confirmation checks."""
        if registry is None or not candidate_calls:
            return []

        logger = get_logger("ToolOrchestrator")
        results: list[dict[str, Any]] = []

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
                logger.warning(f"Attempted execution of unregistered tool '{tool_name}'. Skipping.")
                results.append(
                    {
                        "tool_name": tool_name,
                        "success": False,
                        "output": None,
                        "error": f"Herramienta '{tool_name}' no está registrada en el sistema",
                    }
                )
                call_count += 1
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

    @staticmethod
    def parse_tool_calls(text: str) -> list[tuple[str, dict[str, Any]]]:
        """Parses tool calls from LLM text responses (e.g. <tool name="X">...</tool>)."""
        calls: list[tuple[str, dict[str, Any]]] = []

        # 1. Parse XML <tool name="NAME">BODY</tool> or <tool name="NAME" ... />
        xml_matches = re.findall(
            r"<tool\s+name=[\"']([^\"']+)[\"'](?:\s*\/|>(.*?)</tool>)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        for name, body in xml_matches:
            kwargs: dict[str, Any] = {}
            if body and body.strip():
                try:
                    import json

                    kwargs = json.loads(body.strip())
                except Exception:
                    # Key-value fallback
                    kv_pairs = re.findall(r"(\w+)=[\"']([^\"']+)[\"']", body)
                    for k, v in kv_pairs:
                        kwargs[k] = v
            calls.append((name.strip(), kwargs))

        if calls:
            return calls

        # 2. Parse JSON {"tool": "NAME", "args": {...}}
        try:
            import json

            json_match = re.search(
                r"\{\s*\"tool\"\s*:\s*\"([^\"]+)\"(?:,\s*\"args\"\s*:\s*(\{.*?\}))?\s*\}",
                text,
                re.DOTALL,
            )
            if json_match:
                t_name = json_match.group(1).strip()
                t_args = json.loads(json_match.group(2)) if json_match.group(2) else {}
                calls.append((t_name, t_args))
        except Exception:
            pass

        return calls

    @staticmethod
    def strip_tool_markup(text: str) -> str:
        """Strips raw tool XML or JSON blocks from output text before sending to user/TTS."""
        if not text:
            return ""

        # Remove XML <tool ...></tool> or <tool .../>
        clean = re.sub(
            r"<tool\s+name=[\"'][^\"']+[\"'].*?(?:</tool>|/>)",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Remove markdown JSON tool blocks
        clean = re.sub(
            r"```(?:json)?\s*\{\s*\"tool\"[^\}]+\}\s*```",
            "",
            clean,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Remove hallucinated fake CLI commands and log files
        fake_cmd_pat = r"(?:sonido_test|esonia_test|donilla_test|/var/log/[a-zA-Z0-9_\-\.]+)"
        if re.search(fake_cmd_pat, clean):
            clean = re.sub(fake_cmd_pat, "", clean)
        # Collapse multiple spaces and newlines
        clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
        return clean

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
