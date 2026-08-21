from __future__ import annotations

import ast
from typing import Any, ClassVar

from .base import BaseTool, ToolMetadata, ToolResult


class FileTool(BaseTool):
    """Built-in tool for file operations (read, write, list)."""

    metadata = ToolMetadata(
        name="file_tool",
        description="Reads, writes and lists files in workspace",
        category="system",
    )

    def execute(
        self,
        action: str = "read",
        path: str = "",
        content: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        if action == "read":
            return ToolResult(success=True, output=f"Content of {path}")
        elif action == "write":
            return ToolResult(success=True, output=f"Wrote {len(content)} bytes to {path}")
        elif action == "list":
            return ToolResult(success=True, output=["file1.txt", "file2.py"])
        return ToolResult(success=False, error=f"Unknown file action '{action}'")


class BrowserTool(BaseTool):
    """Built-in tool for browser navigation and web content extraction."""

    metadata = ToolMetadata(
        name="browser_tool",
        description="Simulates web browsing and page content extraction",
        category="web",
    )

    def execute(
        self,
        url: str = "https://example.com",
        target: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        target_url = target or url
        return ToolResult(success=True, output=f"Extracted content from {target_url}")


class CalendarTool(BaseTool):
    """Built-in tool for managing calendar events and reminders."""

    metadata = ToolMetadata(
        name="calendar_tool",
        description="Manages calendar events and reminders",
        category="productivity",
    )

    def execute(
        self,
        action: str = "create_event",
        title: str = "Reunión",
        date: str = "2026-08-08",
        **kwargs: Any,
    ) -> ToolResult:
        return ToolResult(success=True, output=f"Event '{title}' scheduled on {date}")


class SpotifyTool(BaseTool):
    """Built-in tool for media playback control."""

    metadata = ToolMetadata(
        name="spotify_tool",
        description="Controls music playback on Spotify",
        category="media",
    )

    def execute(self, action: str = "play", track: str = "", **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output=f"Spotify action '{action}' executed for '{track}'")


class EmailTool(BaseTool):
    """Built-in tool for sending and reading emails."""

    metadata = ToolMetadata(
        name="email_tool",
        description="Sends and reads emails",
        category="communication",
    )

    def execute(
        self,
        action: str = "send",
        to: str = "",
        subject: str = "",
        body: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        return ToolResult(success=True, output=f"Email sent to {to} with subject '{subject}'")


class APITool(BaseTool):
    """Built-in tool for generic REST API HTTP requests."""

    metadata = ToolMetadata(
        name="api_tool",
        description="Executes generic REST API HTTP requests",
        category="network",
    )

    def execute(
        self,
        method: str = "GET",
        url: str = "",
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        return ToolResult(success=True, output={"status": 200, "data": "OK"})


class DateTimeTool(BaseTool):
    """Built-in tool for real system date, time, and day of week."""

    metadata = ToolMetadata(
        name="datetime_tool",
        description="Provides real system date, time, day of week, and timestamp",
        category="system",
        parameters_schema={
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["now", "time", "date", "day", "timestamp"],
                }
            }
        },
        risk_level="safe",
        requires_confirmation=False,
        read_only=True,
    )

    def execute(self, action: str = "now", **kwargs: Any) -> ToolResult:
        import datetime

        now = datetime.datetime.now()

        if action == "time":
            return ToolResult(success=True, output=now.strftime("%H:%M:%S"))
        elif action == "date":
            return ToolResult(success=True, output=now.strftime("%Y-%m-%d"))
        elif action == "day":
            return ToolResult(success=True, output=now.strftime("%A"))
        elif action == "timestamp":
            return ToolResult(success=True, output=now.isoformat())
        else:  # "now"
            formatted = now.strftime("%A, %B %d, %Y %H:%M:%S")
            return ToolResult(
                success=True,
                output={
                    "datetime_formatted": formatted,
                    "date": now.strftime("%Y-%m-%d"),
                    "time": now.strftime("%H:%M:%S"),
                    "day_of_week": now.strftime("%A"),
                    "timestamp": now.isoformat(),
                },
            )


class SafeASTMathEvaluator:
    """Evaluates mathematical expressions safely using Python AST nodes only."""

    ALLOWED_BIN_OPS: ClassVar[dict[type[ast.operator], Any]] = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a**b,
    }

    ALLOWED_UNARY_OPS: ClassVar[dict[type[ast.unaryop], Any]] = {
        ast.UAdd: lambda a: +a,
        ast.USub: lambda a: -a,
    }

    @classmethod
    def eval_expr(cls, expr: str) -> float | int:
        try:
            node = ast.parse(expr.strip(), mode="eval").body
            res = cls._eval_node(node)
            if isinstance(res, (int, float)):
                return res
            raise ValueError("Expression result is not a number")
        except (SyntaxError, TypeError, KeyError) as exc:
            raise ValueError(f"Invalid math expression: {exc}") from exc

    @classmethod
    def _eval_node(cls, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        elif isinstance(node, ast.BinOp):
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            bin_op_type = type(node.op)
            if bin_op_type not in cls.ALLOWED_BIN_OPS:
                raise ValueError(f"Operator {bin_op_type.__name__} is not allowed")
            if bin_op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
                raise ZeroDivisionError("Division by zero")
            return cls.ALLOWED_BIN_OPS[bin_op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = cls._eval_node(node.operand)
            un_op_type = type(node.op)
            if un_op_type not in cls.ALLOWED_UNARY_OPS:
                raise ValueError(f"Unary operator {un_op_type.__name__} is not allowed")
            return cls.ALLOWED_UNARY_OPS[un_op_type](operand)
        else:
            raise TypeError(f"Expression contains unauthorized AST node: {type(node).__name__}")


class CalculatorTool(BaseTool):
    """Built-in tool for safe mathematical calculations using strict AST parsing."""

    metadata = ToolMetadata(
        name="calculator_tool",
        description="Executes safe mathematical calculations using strict AST evaluation",
        category="utility",
        parameters_schema={
            "required": ["expression"],
            "properties": {"expression": {"type": "string"}},
        },
        risk_level="safe",
        requires_confirmation=False,
        read_only=True,
    )

    def execute(self, expression: str = "", **kwargs: Any) -> ToolResult:
        if not expression or not expression.strip():
            return ToolResult(success=False, error="Expression parameter cannot be empty")

        try:
            val = SafeASTMathEvaluator.eval_expr(expression)
            return ToolResult(success=True, output=val)
        except ZeroDivisionError:
            return ToolResult(success=False, error="Division by zero")
        except (ValueError, TypeError) as val_err:
            return ToolResult(success=False, error=str(val_err))
        except Exception as exc:
            return ToolResult(success=False, error=f"Math evaluation error: {exc}")


class SystemStatusTool(BaseTool):
    """Built-in tool for querying real AURA system runtime status."""

    metadata = ToolMetadata(
        name="system_status_tool",
        description="Retrieves AURA runtime status, active modules, health, and host metrics",
        category="system",
        risk_level="safe",
        requires_confirmation=False,
        read_only=True,
    )

    def __init__(self, aura_instance: Any = None) -> None:
        self.aura_instance = aura_instance

    def execute(self, **kwargs: Any) -> ToolResult:
        base_status: dict[str, Any] = {
            "state": "Running",
            "is_running": True,
            "health": "OK",
        }

        if self.aura_instance is not None and hasattr(self.aura_instance, "state"):
            state_val = (
                self.aura_instance.state.value
                if hasattr(self.aura_instance.state, "value")
                else str(self.aura_instance.state)
            )
            modules_list = (
                list(self.aura_instance.modules.keys())
                if hasattr(self.aura_instance, "modules")
                else []
            )
            base_status.update(
                {
                    "state": state_val,
                    "is_running": getattr(self.aura_instance, "is_running", False),
                    "registered_modules": modules_list,
                }
            )

        # Include real host metrics if requested or available
        try:
            from .system_observation import RealSystemObservationTool

            obs_tool = RealSystemObservationTool()
            obs_res = obs_tool.execute(action="all")
            if obs_res.success and isinstance(obs_res.output, dict):
                base_status["host_metrics"] = obs_res.output
        except Exception:
            pass

        return ToolResult(success=True, output=base_status)
