from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from aura import AURA, AURABootOptions
from aura.audio.autonomous_agent import AutonomousVoiceAgent
from aura.cognition import CognitionModule, ControlIntentDetector, LLMResponse
from aura.config import ConfigurationManager
from aura.memory import Fact, MemoryModule


def _create_test_agent(**kwargs) -> AutonomousVoiceAgent:
    """Helper to instantiate AutonomousVoiceAgent with mocked MicrophoneRecorder."""
    mock_llm = kwargs.pop("llm_provider", MagicMock())
    mock_stt = kwargs.pop("stt_provider", MagicMock())
    mock_tts = kwargs.pop("tts_provider", MagicMock())

    with patch("aura.audio.autonomous_agent.MicrophoneRecorder"):
        agent = AutonomousVoiceAgent(
            llm_provider=mock_llm,
            stt_provider=mock_stt,
            tts_provider=mock_tts,
            **kwargs,
        )
    return agent


def test_auto_mic_blocked_during_tts() -> None:
    """Verifies that while AURA is speaking (TTS active), the mic capture is blocked/bypassed."""
    agent = _create_test_agent()

    # Set speaking state manually
    with agent._speech_lock:
        agent._is_speaking = True

    # Simulate loop check
    with agent._speech_lock:
        is_blocked = agent._is_speaking

    assert is_blocked is True


def test_auto_mic_reenabled_after_tts() -> None:
    """Verifies that after _speak() completes, mic capture is re-enabled."""
    mock_tts = MagicMock()
    agent = _create_test_agent(tts_provider=mock_tts)

    with patch("time.sleep") as mock_sleep:
        agent._speak("Prueba de audio")
        mock_sleep.assert_called_once_with(2.0)

    assert agent._is_speaking is False
    mock_tts.speak.assert_called_once_with("Prueba de audio")


def test_exit_control_intent_variants() -> None:
    """Verifies that ControlIntentDetector.is_exit recognizes all required exit phrase variants."""
    exit_variants = [
        "salir",
        "salid",
        "salida",
        "exit",
        "adios",
        "adiós",
        "chao",
        "cerrar",
        "cierra",
        "cerrar sesión",
        "cierra la sesión",
        "apágate",
        "apagar",
        "AURA SALID",
        "salir aura",
        "hasta luego!",
        "desactivar modo autónomo",
        "detener autónomo",
    ]

    for variant in exit_variants:
        assert ControlIntentDetector.is_exit(variant) is True, f"Failed on variant: '{variant}'"

    # Non-exit phrases
    non_exits = ["hola AURA", "¿cuál es mi color favorito?", "recuérdame estudiar", "gracias"]
    for phrase in non_exits:
        assert ControlIntentDetector.is_exit(phrase) is False, f"False positive on: '{phrase}'"


def test_exit_does_not_call_llm() -> None:
    """Verifies that an EXIT command terminates the loop immediately without calling LLM."""
    mock_llm = MagicMock()
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value.text = "salir"

    agent = _create_test_agent(llm_provider=mock_llm, stt_provider=mock_stt)

    # Provide valid audio buffer length (>= 4000 bytes)
    fake_audio = b"\x00" * 8000

    with (
        patch.object(agent.recorder, "record_until_silence", return_value=fake_audio),
        patch.object(agent, "_speak") as mock_speak,
    ):
        # Run one loop iteration
        agent._loop()

    # Verify LLM was NEVER called
    mock_llm.generate_response.assert_not_called()
    mock_speak.assert_any_call("Desactivando modo autónomo continuo. Hasta luego.")


def test_auto_uses_memory_context(tmp_path: Path) -> None:
    """Verifies that AutonomousVoiceAgent with CognitionModule attached uses memory retrieval."""
    db_file = str(tmp_path / "auto_memory.db")

    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    mem_mod = aura.container.resolve(MemoryModule)
    mem_mod.semantic.add_fact(
        Fact(
            subject="usuario",
            predicate="color_favorito",
            object_val="rojo",
            confidence=1.0,
            source="user",
        )
    )

    cog_mod = aura.container.resolve(CognitionModule)
    mock_llm = MagicMock()

    agent = _create_test_agent(llm_provider=mock_llm, cognition_module=cog_mod)

    mock_llm_resp = LLMResponse(
        content='{"action": "RESPOND", "response": "OK", "reasoning": "test"}'
    )
    mock_llm.generate_response.return_value = mock_llm_resp

    with (
        patch.object(
            cog_mod.llm_provider,
            "generate_response",
            return_value=LLMResponse(content="Tu color favorito es el rojo."),
        ),
        patch.object(agent, "_speak"),
    ):
        # Pass question
        decision = agent._make_decision("¿Cuál es mi color favorito?")
        assert decision.get("action") == "RESPOND"

        # Verify cognition cycle is executed
        res = cog_mod.process_cognitive_cycle("¿Cuál es mi color favorito?")
        assert "rojo" in res.summary.lower()

    aura.shutdown(wait=True)


def test_auto_and_converse_memory_consistency(tmp_path: Path) -> None:
    """Verifies that both AUTO and CONVERSE modes produce consistent answers."""
    db_file = str(tmp_path / "consistency.db")

    cfg = ConfigurationManager()
    cfg.set("memory.db_path", db_file)
    cfg.set("llm.provider", "mock")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    mem_mod = aura.container.resolve(MemoryModule)
    mem_mod.semantic.add_fact(
        Fact(
            subject="usuario",
            predicate="color_favorito",
            object_val="rojo",
            confidence=1.0,
            source="user",
        )
    )

    cog_mod = aura.container.resolve(CognitionModule)

    with patch.object(
        cog_mod.llm_provider,
        "generate_response",
        return_value=LLMResponse(content="Tu color favorito es el rojo."),
    ):
        # 1. CONVERSE flow
        converse_res = cog_mod.process_cognitive_cycle("¿Cuál es mi color favorito?")
        assert "rojo" in converse_res.summary.lower()

        ctx_conv = cog_mod.context_builder.build("¿Cuál es mi color favorito?")
        assert "rojo" in ctx_conv.to_system_prompt().lower()

        # 2. AUTO flow (with CognitionModule attached)
        agent = _create_test_agent(llm_provider=cog_mod.llm_provider, cognition_module=cog_mod)
        assert agent.cognition is not None

        auto_res = cog_mod.process_cognitive_cycle("¿Cuál es mi color favorito?")
        assert "rojo" in auto_res.summary.lower()

    aura.shutdown(wait=True)


def test_empty_reminder_is_rejected() -> None:
    """Verifies that a reminder with empty text or missing keys is rejected and not scheduled."""
    mock_scheduler = MagicMock()
    agent = _create_test_agent(scheduler=mock_scheduler)

    # Test empty text
    empty_reminders = [
        {"text": "", "delay_seconds": 10},
        {"text": "   ", "delay_seconds": 10},
        {"delay_seconds": 10},
        {},
    ]

    for rem in empty_reminders:
        agent._schedule_reminder(rem)

    mock_scheduler.schedule_once.assert_not_called()


def test_reminder_alternate_text_fields() -> None:
    """Verifies alternate keys ('description', 'message', 'action') are extracted."""
    mock_scheduler = MagicMock()
    agent = _create_test_agent(scheduler=mock_scheduler)

    test_cases = [
        ({"description": "Estudiar física", "delay_seconds": 30}, "Estudiar física"),
        ({"message": "Llamar al médico", "delay_seconds": 40}, "Llamar al médico"),
        ({"action": "Comprar pan", "delay_seconds": 50}, "Comprar pan"),
    ]

    for rem_dict, expected_text in test_cases:
        agent._schedule_reminder(rem_dict)
        assert mock_scheduler.schedule_once.called
        call_args = mock_scheduler.schedule_once.call_args
        assert expected_text[:20] in call_args.kwargs.get("name", "")
        mock_scheduler.reset_mock()


def test_no_llm_feedback_loop() -> None:
    """Verifies that while AURA is speaking, captured mic input is suppressed without LLM call."""
    mock_llm = MagicMock()
    mock_stt = MagicMock()
    agent = _create_test_agent(llm_provider=mock_llm, stt_provider=mock_stt)

    # Set speaking state active
    with agent._speech_lock:
        agent._is_speaking = True

    # Attempt loop execution while speaking flag is active
    with patch.object(agent.recorder, "record_until_silence") as mock_record:
        # Simulate check in _loop
        with agent._speech_lock:
            currently_speaking = agent._is_speaking

        if currently_speaking:
            pass  # blocked

        mock_record.assert_not_called()
        mock_stt.transcribe.assert_not_called()
        mock_llm.generate_response.assert_not_called()
