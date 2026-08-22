from __future__ import annotations

from unittest.mock import MagicMock, patch

from aura.cognition import OpenAILLMProvider


def test_openai_provider_generate_response_success():
    provider = OpenAILLMProvider(api_key="fake_groq_key", base_url="https://api.groq.com/openai/v1")

    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "Hola, soy AURA impulsada por Llama 3."
    mock_resp.usage.total_tokens = 15

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch.object(provider, "_get_client", return_value=mock_client):
        res = provider.generate_response("Hola")
        assert res.content == "Hola, soy AURA impulsada por Llama 3."
        assert res.tokens_used == 15


def test_openai_provider_structured_reason():
    provider = OpenAILLMProvider(api_key="fake_key")

    mock_resp = MagicMock()
    mock_resp.choices[
        0
    ].message.content = (
        '{"intent": "greet", "reasoning": "User said hi", "confidence": 0.98, "actions": []}'
    )
    mock_resp.usage.total_tokens = 22

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch.object(provider, "_get_client", return_value=mock_client):
        reason = provider.structured_reason("Hola AURA")
        assert reason["intent"] == "greet"
        assert reason["confidence"] == 0.98


def test_openai_provider_rate_limit_429_handled() -> None:
    """Verifies that HTTP 429 rate limit returns a controlled LLMResponse without infinite loops."""
    provider = OpenAILLMProvider(api_key="fake_groq_key", base_url="https://api.groq.com/openai/v1")

    err = Exception("Rate limit reached for model openai/gpt-oss-120b. HTTP 429")
    err.status_code = 429  # type: ignore[attr-defined]
    err.headers = {"retry-after": "10s"}  # type: ignore[attr-defined]

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = err

    with patch.object(provider, "_get_client", return_value=mock_client):
        res = provider.generate_response("Hola AURA")
        assert res.tokens_used == 0
        assert "Rate Limit 429" in res.content
        assert res.metadata.get("rate_limited") is True
        assert res.metadata.get("status_code") == 429


def test_openai_provider_rate_limit_429_single_retry_success() -> None:
    """Verifies that a short Retry-After triggers ONE retry that succeeds."""
    provider = OpenAILLMProvider(api_key="fake_groq_key", base_url="https://api.groq.com/openai/v1")

    err = Exception("Rate limit reached. HTTP 429")
    err.status_code = 429  # type: ignore[attr-defined]
    err.headers = {"retry-after": "0.1s"}  # type: ignore[attr-defined]

    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "Respuesta recuperada tras retry."
    mock_resp.usage.total_tokens = 10

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [err, mock_resp]

    with (
        patch.object(provider, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
    ):
        res = provider.generate_response("Hola AURA")
        assert res.content == "Respuesta recuperada tras retry."
        assert res.tokens_used == 10
        mock_sleep.assert_called_once_with(0.1)
