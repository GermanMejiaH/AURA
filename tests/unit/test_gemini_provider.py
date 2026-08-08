from __future__ import annotations

from unittest.mock import MagicMock, patch

from aura.cognition import GeminiLLMProvider


def test_gemini_provider_generate_response_success():
    provider = GeminiLLMProvider(api_key="fake_key")

    mock_resp = MagicMock()
    mock_resp.text = "Hola, soy AURA."
    mock_resp.usage_metadata.total_token_count = 12

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp
    mock_client.generate_content.return_value = mock_resp

    with patch.object(provider, "_get_client", return_value=mock_client):
        res = provider.generate_response("Hola")
        assert res.content == "Hola, soy AURA."
        assert res.tokens_used == 12


def test_gemini_provider_missing_api_key():
    provider = GeminiLLMProvider(api_key="")
    err_msg = "GEMINI_API_KEY no encontrada"
    with patch.object(provider, "_get_client", side_effect=ValueError(err_msg)):
        res = provider.generate_response("Hola")
        assert "GEMINI_API_KEY no encontrada" in res.content


def test_gemini_provider_structured_reason():
    provider = GeminiLLMProvider(api_key="fake_key")

    mock_resp = MagicMock()
    mock_resp.text = (
        '{"intent": "greet", "reasoning": "User said hi", "confidence": 0.99, "actions": []}'
    )
    mock_resp.usage_metadata.total_token_count = 20

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp
    mock_client.generate_content.return_value = mock_resp

    with patch.object(provider, "_get_client", return_value=mock_client):
        reason = provider.structured_reason("Hola AURA")
        assert reason["intent"] == "greet"
        assert reason["confidence"] == 0.99
