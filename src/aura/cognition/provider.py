from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    content: str
    tokens_used: int = 0
    raw_response: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract interface for LLM backends (SPEC-001 Section 3.5 & 5.5)."""

    @abstractmethod
    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        context: dict[str, Any] | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    def structured_reason(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class MockLLMProvider(LLMProvider):
    """Mock LLM Provider for offline development and testing."""

    def __init__(self, default_response: str = "AURA understood your request.") -> None:
        self.default_response = default_response
        self.calls: list[dict[str, Any]] = []

    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.calls.append({"prompt": prompt, "system": system_instruction, "context": context})
        return LLMResponse(
            content=f"{self.default_response} [Prompt: {prompt[:30]}...]",
            tokens_used=15,
        )

    def structured_reason(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, "schema": schema, "context": context})
        return {
            "intent": "general_response",
            "reasoning": "Mock provider generated default response.",
            "confidence": 1.0,
            "actions": [],
        }
