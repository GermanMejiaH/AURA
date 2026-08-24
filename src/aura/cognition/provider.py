from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .cognitive_contract import (
    CognitiveMode,
    CognitiveTurnInterpretation,
    ToolCallProposal,
)


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
        max_tokens: int | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    def structured_reason(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def interpret_turn(
        self,
        user_input: str,
        conversation_history: list[dict[str, Any]] | None = None,
        available_tools: list[dict[str, Any]] | None = None,
    ) -> CognitiveTurnInterpretation:
        """Interprets user input turn, generating a strongly typed cognitive proposal.

        Default implementation falls back to structured_reasoning / DIRECT_RESPONSE.
        """
        try:
            res = self.structured_reason(user_input, context={"history": conversation_history})
            actions = res.get("actions", [])
            if actions and isinstance(actions, list) and len(actions) > 0:
                tool_name = str(actions[0])
                args = res.get("arguments", {})
                if not isinstance(args, dict):
                    args = {}
                return CognitiveTurnInterpretation(
                    mode=CognitiveMode.TOOL_PROPOSAL,
                    tool_proposal=ToolCallProposal(tool_name=tool_name, arguments=args),
                    reasoning=res.get("reasoning"),
                    confidence=float(res.get("confidence", 1.0)),
                )
            return CognitiveTurnInterpretation(
                mode=CognitiveMode.DIRECT_RESPONSE,
                direct_response=res.get("reasoning") or f"Entendido: {user_input[:50]}",
                confidence=float(res.get("confidence", 1.0)),
            )
        except Exception as exc:
            return CognitiveTurnInterpretation(
                mode=CognitiveMode.PROVIDER_ERROR,
                error_message=str(exc),
                confidence=0.0,
            )

    def generate_grounded_response(
        self,
        user_input: str,
        tool_name: str,
        tool_output: Any,
        operation_state: str,
        failure_reason: str | None = None,
    ) -> str:
        """Generates natural response grounded strictly in real execution results."""
        if operation_state == "BLOCKED":
            reason_clean = (failure_reason or "").lower()
            if "safe" in reason_clean or "quarantine" in reason_clean:
                return f"AURA está en modo seguro y no puede ejecutar la herramienta '{tool_name}'."
            return (
                f"No tengo autorización o las políticas/gobernanza bloquearon la operación"
                f" '{tool_name}'."
            )
        if operation_state == "FAILED":
            err_msg = failure_reason or "Error desconocido"
            return f"La herramienta '{tool_name}' falló al ejecutarse. Motivo: {err_msg}."
        if operation_state == "COMPLETED":
            return f"Operación '{tool_name}' completada exitosamente con resultado: {tool_output}."
        return f"Operación '{tool_name}' finalizó en estado '{operation_state}'."


class MockLLMProvider(LLMProvider):
    """Mock LLM Provider for offline development and testing."""

    def __init__(
        self,
        default_response: str = "AURA understood your request.",
        mock_interpretations: dict[str, CognitiveTurnInterpretation] | None = None,
    ) -> None:
        self.default_response = default_response
        self.mock_interpretations = mock_interpretations or {}
        self.calls: list[dict[str, Any]] = []

    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        context: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "prompt": prompt,
                "system": system_instruction,
                "context": context,
                "max_tokens": max_tokens,
            }
        )
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

    def interpret_turn(
        self,
        user_input: str,
        conversation_history: list[dict[str, Any]] | None = None,
        available_tools: list[dict[str, Any]] | None = None,
    ) -> CognitiveTurnInterpretation:
        self.calls.append(
            {
                "action": "interpret_turn",
                "user_input": user_input,
                "history": conversation_history,
                "tools": available_tools,
            }
        )
        for key, interp in self.mock_interpretations.items():
            if key.lower() in user_input.lower():
                return interp

        return CognitiveTurnInterpretation(
            mode=CognitiveMode.DIRECT_RESPONSE,
            direct_response=f"{self.default_response} (Input: {user_input})",
            confidence=1.0,
        )

    def generate_grounded_response(
        self,
        user_input: str,
        tool_name: str,
        tool_output: Any,
        operation_state: str,
        failure_reason: str | None = None,
    ) -> str:
        self.calls.append(
            {
                "action": "generate_grounded_response",
                "user_input": user_input,
                "tool_name": tool_name,
                "tool_output": tool_output,
                "operation_state": operation_state,
                "failure_reason": failure_reason,
            }
        )
        return super().generate_grounded_response(
            user_input=user_input,
            tool_name=tool_name,
            tool_output=tool_output,
            operation_state=operation_state,
            failure_reason=failure_reason,
        )
