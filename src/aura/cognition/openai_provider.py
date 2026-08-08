from __future__ import annotations

import os
from typing import Any

from .provider import LLMProvider, LLMResponse


class OpenAILLMProvider(LLMProvider):
    """Universal LLM Provider supporting Groq, Ollama, OpenRouter, and OpenAI.

    Provides ultra-fast, intelligent cloud or local reasoning for AURA.
    """

    SYSTEM_IDENTITY = (
        "Eres AURA (Adaptive Unified Reasoning Assistant), un asistente cognitivo inteligente "
        "y autónomo. Eres conversacional, conciso y siempre respondes en español de forma natural. "
        "Tus respuestas son claras y directas."
    )

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> None:
        from pathlib import Path

        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k and v:
                        os.environ[k] = v

        # Auto-detect endpoints and keys
        resolved_key = (
            api_key
            or os.environ.get("GROQ_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
            or ""
        )
        resolved_url = base_url

        if not resolved_url:
            if os.environ.get("GROQ_API_KEY"):
                resolved_url = "https://api.groq.com/openai/v1"
                model_name = model_name or "llama-3.3-70b-versatile"
            elif os.environ.get("OPENROUTER_API_KEY"):
                resolved_url = "https://openrouter.ai/api/v1"
                model_name = model_name or "meta-llama/llama-3.1-8b-instruct:free"
            else:
                # Default to local Ollama or OpenAI
                resolved_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
                model_name = model_name or "llama3"

        self.api_key = resolved_key or "ollama"
        self.base_url = resolved_url
        self.model_name = model_name or "llama-3.3-70b-versatile"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # type: ignore[import-untyped]

            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Generates a response using the OpenAI-compatible REST API."""
        try:
            client = self._get_client()

            system_content = system_instruction or self.SYSTEM_IDENTITY
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ]

            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            content = response.choices[0].message.content or ""
            tokens = getattr(getattr(response, "usage", None), "total_tokens", len(content) // 4)

            return LLMResponse(
                content=content.strip(),
                tokens_used=tokens,
                raw_response=response,
            )

        except Exception as exc:
            error_msg = str(exc)
            if "api_key" in error_msg.lower() or "401" in error_msg:
                friendly = "API Key no válida o no encontrada. Revisa tu archivo .env."
            elif "connection" in error_msg.lower() or "10061" in error_msg:
                friendly = f"No se pudo conectar con el servidor LLM en {self.base_url}."
            else:
                friendly = f"Error en respuesta LLM: {error_msg[:120]}"

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
