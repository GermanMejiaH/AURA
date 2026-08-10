from __future__ import annotations

from aura.cognition import (
    CognitiveContextBuilder,
    IdentityManager,
    IntentDetector,
    SessionManager,
    WorkingMemory,
)


def test_intent_aware_memory_retrieval_decision() -> None:
    greeting = IntentDetector.detect("Hola AURA")
    assert IntentDetector.should_query_persistent_memory(greeting, "Hola AURA") is False

    farewell = IntentDetector.detect("Chao AURA")
    assert IntentDetector.should_query_persistent_memory(farewell, "Chao AURA") is False

    casual = IntentDetector.detect("Gracias por la ayuda")
    assert IntentDetector.should_query_persistent_memory(casual, "Gracias por la ayuda") is False

    mem_query = IntentDetector.detect("¿Cuál es mi comida favorita?")
    assert (
        IntentDetector.should_query_persistent_memory(mem_query, "¿Cuál es mi comida favorita?")
        is True
    )

    question_personal = IntentDetector.detect("¿Dónde vive mi perro?")
    assert (
        IntentDetector.should_query_persistent_memory(question_personal, "¿Dónde vive mi perro?")
        is True
    )

    question_general = IntentDetector.detect("¿Cuál es la velocidad de la luz?")
    assert (
        IntentDetector.should_query_persistent_memory(
            question_general, "¿Cuál es la velocidad de la luz?"
        )
        is False
    )


def test_topic_extraction_in_intent_detector() -> None:
    intent = IntentDetector.detect("Ahora hablemos de motos")
    assert intent.parameters.get("topic") == "motos"

    intent2 = IntentDetector.detect("Estoy pensando en cocina italiana")
    assert intent2.parameters.get("topic") == "cocina"


def test_session_manager_topic_and_task_management() -> None:
    sm = SessionManager()
    assert sm.get_context().current_topic is None
    assert sm.get_context().active_task is None

    intent1 = IntentDetector.detect("Hablemos de programación")
    sm.update_intent(intent1)
    assert sm.get_context().current_topic == "programación"

    sm.set_task("planificar viaje a Bogotá")
    assert sm.get_context().active_task == "planificar viaje a Bogotá"

    # Turn count increment
    assert sm.record_turn() == 1
    assert sm.record_turn() == 2

    # Clear task
    sm.set_task(None)
    assert sm.get_context().active_task is None


def test_aura_identity_system_prompt_integration() -> None:
    id_mgr = IdentityManager()
    id_mgr.update_identity(name="AURA Voice", personality_style="cálido y conciso")

    builder = CognitiveContextBuilder()
    ctx = builder.build("Hola")
    ctx.identity = id_mgr.get_identity()

    sys_prompt = ctx.to_system_prompt()
    assert "[IDENTIDAD DE AURA]: Nombre: AURA Voice" in sys_prompt
    assert "Estilo: cálido y conciso" in sys_prompt


def test_working_memory_12_turns_limit() -> None:
    wm = WorkingMemory(max_conversation_turns=12)
    for i in range(15):
        wm.add_conversation_turn("user", f"u{i}")
        wm.add_conversation_turn("assistant", f"a{i}")

    turns = wm.get_recent_conversation()
    assert len(turns) == 12
    assert turns[0]["content"] == "u9"
    assert turns[-1]["content"] == "a14"
