from __future__ import annotations

import os
from typing import Any

from .provider import LLMProvider, LLMResponse


class GeminiLLMProvider(LLMProvider):
    """Real LLM Provider using Google Gemini API for AURA's cognitive reasoning."""

    SYSTEM_IDENTITY = (
        "Eres AURA (Adaptive Unified Reasoning Assistant), un asistente cognitivo inteligente "
        "y autónomo. Eres conversacional, conciso y siempre respondes en español. "
        "Eres capaz de razonar, recordar contexto y ayudar con tareas complejas."
    )

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gemini-2.5-flash",
        temperature: float = 0.7,
        max_output_tokens: int = 512,
    ) -> None:
        if not api_key:
            from ..config.manager import ConfigurationManager

            cm = ConfigurationManager()
            cm.load_from_env()
            api_key = os.environ.get("GEMINI_API_KEY", "")

        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "GEMINI_API_KEY no encontrada o inválida. Configúrala con una API Key "
                    "de AI Studio (empieza por AIzaSy):\n"
                    "  $env:GEMINI_API_KEY='tu-api-key'\n"
                    "  Obtén una gratis en: https://aistudio.google.com/app/apikey"
                )

            try:
                from google import genai  # type: ignore

                self._client = genai.Client(api_key=self.api_key)
            except Exception:
                import google.generativeai as genai_legacy  # type: ignore

                genai_any: Any = genai_legacy
                genai_any.configure(api_key=self.api_key)
                self._client = genai_any.GenerativeModel(
                    model_name=self.model_name,
                    generation_config=genai_any.types.GenerationConfig(
                        temperature=self.temperature,
                        max_output_tokens=self.max_output_tokens,
                    ),
                    system_instruction=self.SYSTEM_IDENTITY,
                )
        return self._client

    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Generates a response using the Gemini API."""
        try:
            client = self._get_client()

            full_prompt = prompt
            if system_instruction and system_instruction != self.SYSTEM_IDENTITY:
                full_prompt = f"[Contexto: {system_instruction}]\n\n{prompt}"

            # Modern google-genai SDK
            if hasattr(client, "models"):
                from google.genai import types  # type: ignore

                response = client.models.generate_content(
                    model=self.model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=self.SYSTEM_IDENTITY,
                        temperature=self.temperature,
                        max_output_tokens=self.max_output_tokens,
                    ),
                )
                content = response.text.strip() if response.text else "Sin respuesta del modelo."
                tokens = getattr(response.usage_metadata, "total_token_count", len(content) // 4)
                return LLMResponse(content=content, tokens_used=tokens, raw_response=response)

            # Legacy google-generativeai fallback
            response = client.generate_content(full_prompt)
            content = response.text.strip()
            tokens = getattr(response.usage_metadata, "total_token_count", len(content) // 4)
            return LLMResponse(content=content, tokens_used=tokens, raw_response=response)

        except ValueError as exc:
            return LLMResponse(
                content=str(exc),
                tokens_used=0,
                metadata={"error": "api_key_missing"},
            )
        except Exception as exc:
            error_msg = str(exc)
            if "UNAUTHENTICATED" in error_msg or "ACCESS_TOKEN_TYPE_UNSUPPORTED" in error_msg:
                friendly = (
                    "Error de Autenticación: La clave usada es un token de OAuth. "
                    "Usa una API Key directa (comienza por AIzaSy) creada en https://aistudio.google.com/app/apikey"
                )
            elif "API_KEY_INVALID" in error_msg or "PERMISSION_DENIED" in error_msg:
                friendly = "API Key de Gemini inválida. Verifica GEMINI_API_KEY en .env."
            elif "RESOURCE_EXHAUSTED" in error_msg:
                friendly = "Límite de cuota de Gemini alcanzado. Intenta de nuevo en unos momentos."
            else:
                friendly = f"Error de comunicación con Gemini: {error_msg[:120]}"

            return LLMResponse(
                content=friendly,
                tokens_used=0,
                metadata={"error": error_msg},
            )

    def structured_reason(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Structured reasoning — returns JSON-parseable intent dict."""
        import json

        sys_prompt = (
            "Responde ÚNICAMENTE con un objeto JSON válido con las llaves: "
            "'intent' (string), 'reasoning' (string), 'confidence' (número 0.0-1.0), "
            "'actions' (lista de strings). Sin markdown, sin explicaciones extra."
        )
        result = self.generate_response(prompt, system_instruction=sys_prompt, context=context)

        raw = result.content.strip().removeprefix("```json").removesuffix("```").strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        return {
            "intent": "general_response",
            "reasoning": result.content,
            "confidence": 0.90,
            "actions": [],
        }
