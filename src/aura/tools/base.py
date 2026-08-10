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
    risk_level: str = "safe"  # "safe", "reversible", "destructive"
    requires_confirmation: bool = False
    read_only: bool = True

    def __post_init__(self) -> None:
        valid_risks = {"safe", "reversible", "destructive"}
        if self.risk_level not in valid_risks:
            self.risk_level = "safe"


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
