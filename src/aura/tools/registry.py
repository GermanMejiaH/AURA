from __future__ import annotations

import time

from .base import BaseTool, ToolMetadata, ToolResult


class ToolRegistry:
    """Registry managing external tools and safe execution dispatch."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        name = tool.metadata.name.lower()
        self._tools[name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name.lower())

    def list_metadata(self) -> list[ToolMetadata]:
        return [tool.metadata for tool in self._tools.values()]

    def validate_parameters(self, tool_name: str, **kwargs: object) -> tuple[bool, str | None]:
        """Validates parameter kwargs against tool metadata parameters_schema."""
        tool = self.get(tool_name)
        if tool is None:
            return False, f"Tool '{tool_name}' not found in registry"

        schema = tool.metadata.parameters_schema
        if not schema:
            return True, None

        # Check required fields
        required = schema.get("required", [])
        if isinstance(required, list):
            for req in required:
                if req not in kwargs or kwargs[req] is None:
                    return False, f"Missing required parameter '{req}' for tool '{tool_name}'"

        # Check types if properties schema is declared
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            type_map: dict[str, type | tuple[type, ...]] = {
                "string": str,
                "str": str,
                "integer": int,
                "int": int,
                "float": (int, float),
                "number": (int, float),
                "boolean": bool,
                "bool": bool,
                "dict": dict,
                "list": list,
            }
            for param_name, param_val in kwargs.items():
                if param_name in properties and isinstance(properties[param_name], dict):
                    expected_type_str = properties[param_name].get("type")
                    if expected_type_str in type_map:
                        expected_type = type_map[expected_type_str]
                        if not isinstance(param_val, expected_type):
                            return (
                                False,
                                f"Parameter '{param_name}' must be of type {expected_type_str}, "
                                f"got {type(param_val).__name__}",
                            )

                    # Check enum values if defined
                    enum_vals = properties[param_name].get("enum")
                    if isinstance(enum_vals, list) and param_val not in enum_vals:
                        return (
                            False,
                            f"Parameter '{param_name}' value '{param_val}' "
                            f"not in allowed enum {enum_vals}",
                        )

        return True, None

    def execute(self, tool_name: str, **kwargs: object) -> ToolResult:
        tool = self.get(tool_name)
        if tool is None:
            return ToolResult(success=False, error=f"Tool '{tool_name}' not found in registry")

        valid, val_err = self.validate_parameters(tool_name, **kwargs)
        if not valid:
            return ToolResult(
                success=False,
                error=val_err or f"Parameter validation failed for '{tool_name}'",
            )

        start_t = time.perf_counter()
        try:
            res = tool.execute(**kwargs)
        except Exception as exc:
            elapsed = round((time.perf_counter() - start_t) * 1000, 2)
            return ToolResult(success=False, error=str(exc), execution_time_ms=elapsed)
        else:
            res.execution_time_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return res
