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
    mock_resp.choices[0].message.content = (
        '{"intent": "greet", "reasoning": "User said hi", "confidence": 0.98, "actions": []}'
    )
    mock_resp.usage.total_tokens = 22

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch.object(provider, "_get_client", return_value=mock_client):
        reason = provider.structured_reason("Hola AURA")
        assert reason["intent"] == "greet"
        assert reason["confidence"] == 0.98
