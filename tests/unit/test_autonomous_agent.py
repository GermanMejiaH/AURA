from __future__ import annotations

from unittest.mock import MagicMock

from aura.audio import AutonomousVoiceAgent


def test_autonomous_voice_agent_initialization():
    mock_llm = MagicMock()
    agent = AutonomousVoiceAgent(llm_provider=mock_llm)

    assert not agent.is_active()
    assert not agent._is_speaking


def test_autonomous_voice_agent_decision_making():
    mock_llm = MagicMock()
    mock_llm.generate_response.return_value = MagicMock(
        content='{"action": "RESPOND", "response": "Hola", "reasoning": "User greeted"}'
    )

    agent = AutonomousVoiceAgent(llm_provider=mock_llm)
    decision = agent._make_decision("Hola AURA")

    assert decision["action"] == "RESPOND"
    assert decision["response"] == "Hola"


def test_autonomous_voice_agent_interruption():
    mock_llm = MagicMock()
    agent = AutonomousVoiceAgent(llm_provider=mock_llm)

    agent._is_speaking = True
    agent.interrupt_speaking()

    assert not agent._is_speaking
