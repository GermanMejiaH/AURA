from __future__ import annotations

import os
from typing import Any

from .provider import LLMProvider, LLMResponse


class OpenAILLMProvider(LLMProvider):
    """Universal LLM Provider supporting Groq, Ollama, OpenRouter, and OpenAI.

    Provides ultra-fast, intelligent cloud or local reasoning for AURA.
    """

    DEFAULT_CONVERSATION_MAX_TOKENS = 150

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
        max_tokens: int = DEFAULT_CONVERSATION_MAX_TOKENS,
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
                model_name = model_name or "groq/compound"
            elif os.environ.get("OPENROUTER_API_KEY"):
                resolved_url = "https://openrouter.ai/api/v1"
                model_name = model_name or "meta-llama/llama-3.1-8b-instruct:free"
            else:
                # Default to local Ollama or OpenAI
                resolved_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
                model_name = model_name or "llama3"

        self.api_key = resolved_key or "ollama"
        self.base_url = resolved_url
        self.model_name = model_name or "groq/compound"
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

    @staticmethod
    def _to_int(val: Any) -> int:
        return int(val) if isinstance(val, (int, float)) else 0

    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        context: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generates a response using the OpenAI-compatible REST API."""
        import time

        from ..logging import get_logger
        from ..telemetry import TelemetryManager

        logger = get_logger("OpenAILLMProvider")
        telemetry = TelemetryManager.get_instance()
        start_t = time.perf_counter()
        req_max_tokens = max_tokens if max_tokens is not None else self.max_tokens

        try:
            client = self._get_client()

            system_content = system_instruction or self.SYSTEM_IDENTITY
            from .context import estimate_tokens

            # Hard Ceiling Protection (2,000 tokens ceiling)
            max_provider_tokens = 2000
            curr_prompt = prompt
            combined_text = system_content + "\n" + curr_prompt
            est_tokens = estimate_tokens(combined_text)

            # Truncate prompt text if combined tokens exceed max_provider_tokens ceiling
            if est_tokens > max_provider_tokens:
                # Target max chars based on 2.0 chars/token ratio (~4,000 chars total)
                target_prompt_chars = max(200, (max_provider_tokens * 2) - len(system_content))
                curr_prompt = curr_prompt[-target_prompt_chars:]
                combined_text = system_content + "\n" + curr_prompt
                est_tokens = estimate_tokens(combined_text)
                logger.warning(
                    f"Prompt payload truncated to fit max_provider_tokens ({max_provider_tokens}). "
                    f"New prompt_chars={len(curr_prompt)} est_tokens={est_tokens}"
                )

            sys_chars = len(system_content)
            sys_toks = estimate_tokens(system_content)
            prompt_chars = len(curr_prompt)
            prompt_toks = estimate_tokens(curr_prompt)
            combined_chars = len(combined_text)

            logger.info(
                f"[PAYLOAD SENT] [PAYLOAD BREAKDOWN] system_chars={sys_chars} ({sys_toks}t) "
                f"prompt_chars={prompt_chars} ({prompt_toks}t) "
                f"combined_chars={combined_chars} total_est_tokens={est_tokens}"
            )

            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": curr_prompt},
            ]

            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=req_max_tokens,
            )

            content = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)

            from .context import estimate_tokens

            prompt_tokens = self._to_int(getattr(usage, "prompt_tokens", 0))
            if prompt_tokens <= 0:
                prompt_tokens = estimate_tokens(system_content + prompt)

            completion_tokens = self._to_int(getattr(usage, "completion_tokens", 0))
            if completion_tokens <= 0:
                completion_tokens = estimate_tokens(content)

            tokens = self._to_int(getattr(usage, "total_tokens", 0))
            if tokens <= 0:
                tokens = prompt_tokens + completion_tokens

            logger.info(
                f"[LLM TOKENS] prompt_tokens={prompt_tokens} "
                f"max_tokens={req_max_tokens} completion_tokens={completion_tokens}"
            )
            telemetry.record_token_usage(
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
            )

            elapsed_ms = (time.perf_counter() - start_t) * 1000
            telemetry.increment("llm_calls_total")
            telemetry.increment("llm_calls_success")
            telemetry.record_latency("time_llm_ms", elapsed_ms)

            return LLMResponse(
                content=content.strip(),
                tokens_used=tokens,
                raw_response=response,
            )

        except Exception as exc:
            from ..logging import get_logger

            logger = get_logger("OpenAILLMProvider")
            error_msg = str(exc)
            status_code = getattr(
                exc,
                "status_code",
                429 if ("429" in error_msg or "rate" in error_msg.lower()) else None,
            )

            headers = getattr(exc, "headers", {}) or getattr(
                getattr(exc, "response", None), "headers", {}
            )
            retry_after_val = headers.get("retry-after") or headers.get("x-ratelimit-reset-tokens")
            remaining_tokens = headers.get("x-ratelimit-remaining-tokens")

            elapsed_ms = (time.perf_counter() - start_t) * 1000
            telemetry.increment("llm_calls_total")
            telemetry.increment("llm_calls_failed")
            telemetry.record_latency("time_llm_ms", elapsed_ms)

            if status_code == 429 or "429" in error_msg or "rate" in error_msg.lower():
                telemetry.increment("llm_rate_limit_429")
                logger.warning(
                    f"HTTP 429 Rate Limit hit [provider=OpenAILLMProvider, "
                    f"base_url={self.base_url}, model={self.model_name}, status=429, "
                    f"error={error_msg[:150]}, retry_after={retry_after_val}, "
                    f"remaining_tokens={remaining_tokens}]"
                )

                # Retry schedule: Retry #1 at 1s, Retry #2 at 2s
                retry_delays = [1.0, 2.0]
                if retry_after_val:
                    try:
                        parsed_delay = float(str(retry_after_val).rstrip("s"))
                        if 0 < parsed_delay <= 5.0:
                            retry_delays = [parsed_delay]
                    except ValueError:
                        pass

                for attempt, delay in enumerate(retry_delays, start=1):
                    logger.info(
                        f"Retrying LLM request (Attempt #{attempt}) after {delay:.1f}s delay..."
                    )
                    time.sleep(delay)
                    try:
                        client = self._get_client()
                        response = client.chat.completions.create(
                            model=self.model_name,
                            messages=messages,
                            temperature=self.temperature,
                            max_tokens=req_max_tokens,
                        )
                        content = response.choices[0].message.content or ""
                        retry_usage = getattr(response, "usage", None)
                        p_toks = self._to_int(getattr(retry_usage, "prompt_tokens", 0))
                        if p_toks <= 0:
                            p_toks = len(system_content + prompt) // 4
                        c_toks = self._to_int(getattr(retry_usage, "completion_tokens", 0))
                        if c_toks <= 0:
                            c_toks = len(content) // 4
                        tot_toks = self._to_int(getattr(retry_usage, "total_tokens", 0))
                        if tot_toks <= 0:
                            tot_toks = p_toks + c_toks
                        logger.info(
                            f"[LLM TOKENS] prompt_tokens={p_toks} "
                            f"max_tokens={req_max_tokens} completion_tokens={c_toks}"
                        )
                        telemetry.record_token_usage(prompt_tokens=p_toks, completion_tokens=c_toks)
                        return LLMResponse(
                            content=content.strip(),
                            tokens_used=tot_toks,
                            raw_response=response,
                        )
                    except Exception as retry_exc:
                        logger.warning(f"Retry #{attempt} after 429 failed: {retry_exc}")
                        error_msg = str(retry_exc)

                logger.warning("[LLM] Rate limit fallback activated")
                friendly = (
                    "Rate Limit 429: Estoy experimentando alta demanda en este momento. "
                    "Inténtalo nuevamente en unos segundos."
                )
            elif "api_key" in error_msg.lower() or "401" in error_msg:
                friendly = "API Key no válida o no encontrada. Revisa tu archivo .env."
            elif "connection" in error_msg.lower() or "10061" in error_msg:
                friendly = f"No se pudo conectar con el servidor LLM en {self.base_url}."
            else:
                friendly = f"Error en respuesta LLM: {error_msg[:120]}"

            return LLMResponse(
                content=friendly,
                tokens_used=0,
                metadata={
                    "error": error_msg,
                    "status_code": status_code or 500,
                    "rate_limited": (status_code == 429),
                },
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
