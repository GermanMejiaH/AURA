from __future__ import annotations

from aura.cognition import CognitionModule, MockLLMProvider
from aura.tools.builtins import DateTimeTool
from aura.tools.registry import ToolRegistry


def test_caso_a_conversational_continuity() -> None:
    cognition = CognitionModule(llm_provider=MockLLMProvider("Respuesta"))
    cognition.on_initialize()

    # Turn 1
    cognition.session_manager.set_topic("GPU")
    cognition.process_cognitive_cycle("Estoy pensando en comprar una GPU")

    # Turn 2
    cognition.session_manager.set_active_entity("GTX 1650")
    cognition.process_cognitive_cycle("Tengo una GTX 1650")

    # Turn 3
    res = cognition.process_cognitive_cycle("¿Cuál me recomiendas?")

    # Verify context built for cycle
    assert res.summary.startswith("Respuesta")
    history = cognition.working_memory.get_recent_conversation()
    assert len(history) == 6  # 3 user + 3 assistant turns


def test_caso_b_topic_change() -> None:
    cognition = CognitionModule(llm_provider=MockLLMProvider("Respuesta"))
    cognition.on_initialize()

    # Motos topic
    cognition.session_manager.set_topic("motos")
    cognition.process_cognitive_cycle("Estoy mirando motos")
    cognition.process_cognitive_cycle("Tengo una DT 125")

    # Topic change to PC
    cognition.session_manager.set_topic("PC")
    cognition.session_manager.set_active_entity("GTX 1650")
    cognition.process_cognitive_cycle("Ahora quiero hablar de mi PC")
    cognition.process_cognitive_cycle("Tengo una GTX 1650")

    res = cognition.process_cognitive_cycle("¿Qué me recomiendas?")
    assert res.summary.startswith("Respuesta")
    assert cognition.session_manager.get_context().current_topic == "PC"


def test_caso_c_ambiguous_reference() -> None:
    cognition = CognitionModule(llm_provider=MockLLMProvider("Aclaración"))
    cognition.on_initialize()

    # Setup history with 2 recent entities
    cognition.working_memory.add_conversation_turn(
        "user", "Veo una Yamaha MT-07 y una Honda CB650R"
    )

    from aura.cognition import ConversationContext
    from aura.cognition.conversation_context import AnaphoraResolution

    anaphora_ambiguous = AnaphoraResolution(
        resolved_entity=None,
        is_ambiguous=True,
        candidate_entities=["Yamaha MT-07", "Honda CB650R"],
        requires_reference=True,
    )

    conv_ctx = cognition.context_builder.build(
        input_text="¿Cuál de las dos me recomiendas?",
        working_memory=cognition.working_memory,
    )

    conv_ctx.conversation_context = ConversationContext(
        anaphora_resolution=anaphora_ambiguous,
        relevant_turns=cognition.working_memory.get_recent_conversation(),
    )

    prompt = conv_ctx.to_system_prompt()
    assert "[REFERENCIA ACTIVA]: AMBIGUA — SE REQUIERE ACLARACIÓN" in prompt


def test_caso_d_no_context_clean_prompt() -> None:
    cognition = CognitionModule(llm_provider=MockLLMProvider("Hola"))
    cognition.on_initialize()

    res = cognition.process_cognitive_cycle("Hola AURA")
    assert res.summary.startswith("Hola")


def test_caso_e_tool_orchestration_datetime() -> None:
    cognition = CognitionModule(llm_provider=MockLLMProvider("Son las 10:00 AM"))
    cognition.on_initialize()

    # Register DateTimeTool in container
    if cognition._container is not None:
        reg = ToolRegistry()
        reg.register(DateTimeTool())
        cognition._container.register(ToolRegistry, instance=reg)

    res = cognition.process_cognitive_cycle("¿Qué hora es?")
    assert res.summary.startswith("Son las 10:00 AM")
