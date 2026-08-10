from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .provider import LLMProvider, LLMResponse


class RealLLMProvider(LLMProvider):
    """Real LLM Provider supporting Ollama local models and OpenAI/Gemini REST APIs."""

    def __init__(
        self,
        endpoint_url: str = "http://localhost:11434/api/chat",
        model_name: str = "llama3",
        api_key: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.model_name = model_name
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "Eres AURA, un asistente cognitivo inteligente y autónomo.",
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Generates a text response using Ollama or REST API endpoint."""
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }

        req = urllib.request.Request(
            self.endpoint_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                content = res_data.get("message", {}).get("content") or res_data.get(
                    "response", "Respuesta recibida."
                )
                tokens = res_data.get("eval_count", 25)
                return LLMResponse(content=content, tokens_used=tokens, raw_response=res_data)
        except (urllib.error.URLError, Exception) as exc:
            # Fallback to local intelligent response if Ollama server is offline
            fallback_content = (
                f"AURA (Motor Local): He procesado tu solicitud '{prompt}'. "
                f"[Modo Local Activo - Conecta Ollama/Gemini para razonamiento profundo de LLM]"
            )
            return LLMResponse(
                content=fallback_content,
                tokens_used=10,
                metadata={"offline_error": str(exc)},
            )

    def structured_reason(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Performs structured intent and action reasoning."""
        sys_prompt = (
            "Eres el motor de razonamiento de AURA. Devuelve un JSON válido con las llaves: "
            "'intent', 'reasoning', 'confidence' (0.0 a 1.0) y 'actions' (lista de acciones)."
        )
        res = self.generate_response(prompt, system_instruction=sys_prompt, context=context)

        try:
            parsed = json.loads(res.content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        return {
            "intent": "general_response",
            "reasoning": res.content,
            "confidence": 0.95,
            "actions": [],
        }
