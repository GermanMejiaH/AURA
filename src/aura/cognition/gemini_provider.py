"""Stage 21 — Real Gemini Cognitive Provider Integration.

Implements GeminiLLMProvider extending LLMProvider using official Google GenAI SDK (google-genai)
or raw REST fallback for structured cognitive reasoning and grounded response generation.
"""

from __future__ import annotations

import json
import os
from typing import Any

from aura.logging import get_logger

from .cognitive_contract import (
    CognitiveMode,
    CognitiveTurnInterpretation,
    ToolCallProposal,
)
from .provider import LLMProvider, LLMResponse

logger = get_logger("GeminiLLMProvider")


class GeminiLLMProvider(LLMProvider):
    """Real Cognitive LLM Provider for Google Gemini models (Gemini 2.5 Flash / Pro)."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gemini-2.5-flash",
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model_name = model_name
        self.client: Any = None

        if self.api_key:
            try:
                from google import genai

                self.client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                logger.warning(
                    f"Failed to initialize google.genai Client: {exc}. Will use REST/mock fallback."
                )

    def _get_client(self) -> Any:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY no encontrada")
        if self.client is None:
            try:
                from google import genai

                self.client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                raise ValueError(f"Failed to initialize google.genai Client: {exc}") from exc
        return self.client

    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Generates text completion via Google Gemini model."""
        try:
            client = self._get_client()
        except ValueError as val_err:
            return LLMResponse(
                content=f"[GeminiLLMProvider Offline Fallback]: {val_err}",
                tokens_used=0,
            )

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=system_instruction if system_instruction else None,
                temperature=0.2,
            )

            res = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            text_out = res.text if hasattr(res, "text") and res.text else str(res)
            tokens = 0
            if hasattr(res, "usage_metadata") and res.usage_metadata is not None:
                if isinstance(res.usage_metadata, dict):
                    tokens = res.usage_metadata.get("total_token_count", 0)
                else:
                    tokens = getattr(res.usage_metadata, "total_token_count", 0)

            return LLMResponse(
                content=text_out,
                tokens_used=int(tokens) if isinstance(tokens, (int, float)) else 0,
                raw_response=res,
            )
        except Exception as exc:
            logger.error(f"Gemini API generate_content error: {exc}")
            return LLMResponse(
                content=f"[Gemini Error Fallback]: {exc}",
                tokens_used=0,
            )

    def structured_reason(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generates structured JSON reasoning output via Gemini model."""
        if not self.api_key or not self.client:
            return {
                "intent": "general_response",
                "reasoning": "Gemini API key not configured.",
                "confidence": 0.5,
                "actions": [],
            }

        sys_prompt = (
            "Eres el motor de razonamiento estructurado de AURA.\n"
            "Responde ÚNICAMENTE en formato JSON estricto sin bloques markdown de código."
        )

        resp = self.generate_response(prompt=prompt, system_instruction=sys_prompt)
        text = resp.content.strip()

        # Clean markdown fenced blocks ```json ... ```
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:
            logger.warning(f"Failed to parse structured JSON from Gemini response: {exc}")

        return {
            "intent": "general_response",
            "reasoning": text[:200],
            "confidence": 0.8,
            "actions": [],
        }

    def interpret_turn(
        self,
        user_input: str,
        conversation_history: list[dict[str, Any]] | None = None,
        available_tools: list[dict[str, Any]] | None = None,
    ) -> CognitiveTurnInterpretation:
        """Interprets user turn using Gemini, outputting a typed CognitiveTurnInterpretation."""
        if not self.api_key:
            return CognitiveTurnInterpretation(
                mode=CognitiveMode.PROVIDER_ERROR,
                error_message="GEMINI_API_KEY no configurada.",
                confidence=0.0,
            )

        tools_str = ""
        if available_tools:
            tools_desc = []
            for t in available_tools:
                tools_desc.append(
                    f"- {t.get('name')}: {t.get('description')} (schema:"
                    f" {t.get('parameters_schema')})"
                )
            tools_str = "\nHerramientas Disponibles:\n" + "\n".join(tools_desc)

        hist_str = ""
        if conversation_history:
            turns = []
            for h in conversation_history[-5:]:
                turns.append(f"{h.get('role', 'user')}: {h.get('content', '')}")
            hist_str = "\nHistorial Reciente:\n" + "\n".join(turns)

        sys_prompt = (
            "Eres el componente de razonamiento cognitivo de AURA.\n"
            "TUS RESPUESTAS SON PROPUESTAS UNICAMENTE. NO TIENES AUTORIDAD DE EJECUCIÓN.\n"
            "Responde ÚNICAMENTE con un objeto JSON válido sin markdown con las llaves:\n"
            "{\n"
            '  "mode": "tool_proposal" | "direct_response" | "clarification_required" |'
            ' "unsupported",\n'
            '  "direct_response": "texto si mode es direct_response o clarification_required",\n'
            '  "tool_name": "nombre exacto de herramienta si mode es tool_proposal",\n'
            '  "arguments": { diccionarios de argumentos para la herramienta },\n'
            '  "reasoning": "explicación breve de la propuesta",\n'
            '  "confidence": 0.95\n'
            "}"
        )

        full_prompt = (
            f'Entrada del Usuario: "{user_input}"\n'
            f"{hist_str}\n"
            f"{tools_str}\n\n"
            "Genera la interpretación en JSON estricto:"
        )

        try:
            resp = self.generate_response(prompt=full_prompt, system_instruction=sys_prompt)
            clean_text = resp.content.strip()
            if clean_text.startswith("```"):
                clean_lines = clean_text.splitlines()
                if clean_lines[0].startswith("```"):
                    clean_lines = clean_lines[1:]
                if clean_lines and clean_lines[-1].startswith("```"):
                    clean_lines = clean_lines[:-1]
                clean_text = "\n".join(clean_lines).strip()

            data = json.loads(clean_text)
            mode_str = str(data.get("mode", "direct_response")).strip().lower()

            mode_enum = CognitiveMode.DIRECT_RESPONSE
            if mode_str == "tool_proposal":
                mode_enum = CognitiveMode.TOOL_PROPOSAL
            elif mode_str == "clarification_required":
                mode_enum = CognitiveMode.CLARIFICATION_REQUIRED
            elif mode_str == "unsupported":
                mode_enum = CognitiveMode.UNSUPPORTED

            tool_proposal: ToolCallProposal | None = None
            if mode_enum == CognitiveMode.TOOL_PROPOSAL:
                t_name = str(data.get("tool_name", "")).strip()
                t_args = data.get("arguments", {})
                if not isinstance(t_args, dict):
                    t_args = {}
                tool_proposal = ToolCallProposal(tool_name=t_name, arguments=t_args)

            return CognitiveTurnInterpretation(
                mode=mode_enum,
                tool_proposal=tool_proposal,
                direct_response=data.get("direct_response"),
                reasoning=data.get("reasoning"),
                confidence=float(data.get("confidence", 0.9)),
            )

        except Exception as exc:
            logger.warning(f"Failed cognitive interpretation from Gemini: {exc}")
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
        """Generates a natural language response grounded strictly in real execution results."""
        if not self.api_key or not self.client:
            return super().generate_grounded_response(
                user_input=user_input,
                tool_name=tool_name,
                tool_output=tool_output,
                operation_state=operation_state,
                failure_reason=failure_reason,
            )

        if operation_state == "BLOCKED":
            reason_clean = (failure_reason or "").lower()
            if "safe" in reason_clean or "quarantine" in reason_clean:
                return f"AURA está en modo seguro y no puede ejecutar la herramienta '{tool_name}'."
            return (
                f"No puedo ejecutar esa acción porque fue bloqueada por política/gobernanza:"
                f" {failure_reason or 'No autorizado'}."
            )
        if operation_state == "FAILED":
            err_msg = failure_reason or "Error en herramienta"
            return f"La operación '{tool_name}' falló al ejecutarse. Motivo: {err_msg}."

        sys_prompt = (
            "Eres AURA. Genera una respuesta natural y concisa en español basada ESTRICTAMENTE"
            " en el resultado real de la ejecución. NO INVENTES NADA QUE NO ESTÉ EN EL RESULTADO."
        )
        output_repr = (
            json.dumps(tool_output, ensure_ascii=False)
            if isinstance(tool_output, (dict, list))
            else str(tool_output)
        )
        prompt = (
            f'Usuario: "{user_input}"\n'
            f"Herramienta Ejecutada: {tool_name}\n"
            f"Estado de Operación: {operation_state}\n"
            f"Resultado Real de Ejecución: {output_repr}\n\n"
            "Genera la respuesta natural final grounded:"
        )

        try:
            resp = self.generate_response(prompt=prompt, system_instruction=sys_prompt)
            if resp.content and not resp.content.startswith("[Gemini Error"):
                return resp.content.strip()
        except Exception as exc:
            logger.warning(f"Failed to generate grounded response from Gemini: {exc}")

        return super().generate_grounded_response(
            user_input=user_input,
            tool_name=tool_name,
            tool_output=tool_output,
            operation_state=operation_state,
            failure_reason=failure_reason,
        )
