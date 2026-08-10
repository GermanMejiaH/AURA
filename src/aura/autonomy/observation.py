from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..tools.base import ToolResult


@dataclass
class Observation:
    """Represents structured output observation captured after executing an AgentTask or Tool."""

    task_id: str
    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_tool_result(cls, task_id: str, tool_result: ToolResult) -> Observation:
        """Constructs an Observation instance cleanly from a ToolResult."""
        return cls(
            task_id=task_id,
            success=tool_result.success,
            output=tool_result.output,
            error=tool_result.error,
            metadata={"execution_time_ms": tool_result.execution_time_ms},
        )
