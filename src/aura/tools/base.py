from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolMetadata:
    name: str
    description: str
    category: str = "general"
    parameters_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    success: bool
    output: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0


class BaseTool(ABC):
    """Abstract base class for all AURA external tools and capabilities."""

    metadata: ToolMetadata

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult: ...
