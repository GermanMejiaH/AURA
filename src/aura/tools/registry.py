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

    def execute(self, tool_name: str, **kwargs: object) -> ToolResult:
        tool = self.get(tool_name)
        if tool is None:
            return ToolResult(success=False, error=f"Tool '{tool_name}' not found in registry")

        start_t = time.perf_counter()
        try:
            res = tool.execute(**kwargs)
        except Exception as exc:
            elapsed = round((time.perf_counter() - start_t) * 1000, 2)
            return ToolResult(success=False, error=str(exc), execution_time_ms=elapsed)
        else:
            res.execution_time_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return res
