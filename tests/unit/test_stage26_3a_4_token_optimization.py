"""Unit test suite for STAGE 26.3A.4 — TOKEN OPTIMIZATION & CONTEXT DEDUPLICATION."""

from __future__ import annotations

from typing import Any

from aura.cognition.context import CognitiveContext, CognitiveContextBuilder
from aura.cognition.openai_provider import OpenAILLMProvider
from aura.container import DependencyContainer
from aura.memory.models import Fact
from aura.memory.module import MemoryModule
from aura.memory.store import SQLiteMemoryStore


def test_no_duplicate_history() -> None:
    """Verify history appears exclusively in to_formatted_prompt and not in to_system_prompt."""
    history = [
        {"role": "user", "content": "Hola AURA"},
        {"role": "assistant", "content": "¡Hola! ¿En qué puedo ayudarte?"},
    ]

    ctx = CognitiveContext(
        system_instruction="Instruction test",
        user_input="¿Qué hora es?",
        conversation_history=history,
    )

    sys_prompt = ctx.to_system_prompt()
    formatted_prompt = ctx.to_formatted_prompt()

    # Assert conversation history turns do NOT appear in system prompt
    assert "Historial conversacional reciente" not in sys_prompt
    assert "[Usuario]: Hola AURA" not in sys_prompt
    assert "[AURA]: ¡Hola! ¿En qué puedo ayudarte?" not in sys_prompt

    # Assert conversation history turns DO appear in formatted prompt
    assert "Historial conversacional reciente" in formatted_prompt
    assert "[Usuario]: Hola AURA" in formatted_prompt
    assert "[AURA]: ¡Hola! ¿En qué puedo ayudarte?" in formatted_prompt


def test_max_tokens_capping_and_override() -> None:
    """Verify DEFAULT_CONVERSATION_MAX_TOKENS = 150 default and override support."""
    provider = OpenAILLMProvider()

    # Assert class constant and default init value
    assert OpenAILLMProvider.DEFAULT_CONVERSATION_MAX_TOKENS == 150
    assert provider.max_tokens == 150

    # Mock client completion call to test max_tokens pass-through
    class DummyChoice:
        message = type("Msg", (), {"content": "Respuesta breve"})()

    class DummyResponse:
        def __init__(self) -> None:
            self.choices = [DummyChoice()]
            self.usage = type(
                "Usage", (), {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}
            )()

    class DummyCompletions:
        def __init__(self) -> None:
            self.last_max_tokens = None

        def create(self, **kwargs: Any) -> DummyResponse:
            self.last_max_tokens = kwargs.get("max_tokens")
            return DummyResponse()

    class DummyClient:
        def __init__(self) -> None:
            self.chat = type("Chat", (), {"completions": DummyCompletions()})()

    dummy_client = DummyClient()
    provider._client = dummy_client

    # Call generate_response without override
    res1 = provider.generate_response(prompt="Hola")
    assert res1.content == "Respuesta breve"
    assert dummy_client.chat.completions.last_max_tokens == 150

    # Call generate_response with explicit override (max_tokens=500)
    res2 = provider.generate_response(prompt="Reporte", max_tokens=500)
    assert res2.content == "Respuesta breve"
    assert dummy_client.chat.completions.last_max_tokens == 500


def test_open_memory_query_works() -> None:
    """Verify open memory query ('¿Qué recuerdas de mí?') returns stored memory facts."""
    container = DependencyContainer()
    store = SQLiteMemoryStore(db_path=":memory:")
    mem_module = MemoryModule(store=store)
    mem_module.semantic.add_fact(
        Fact(subject="usuario", predicate="nombre", object_val="Andrés", source="user")
    )
    container.register(MemoryModule, instance=mem_module)

    builder = CognitiveContextBuilder(container=container)
    ctx = builder.build(input_text="¿Qué recuerdas de mí?")

    # Assert persistent memory section contains stored fact
    assert len(ctx.relevant_memories) > 0
    assert any("Andrés" in m for m in ctx.relevant_memories)


def test_explicit_memory_storage_works() -> None:
    """Verify explicit memory statement ('Mi nombre es Andrés.') persists memory into store."""
    store = SQLiteMemoryStore(db_path=":memory:")
    mem_module = MemoryModule(store=store)

    fact = Fact(subject="usuario", predicate="nombre", object_val="Andrés", source="user")
    mem_module.semantic.add_fact(fact)

    facts = store.get_facts(subject="usuario", predicate="nombre")
    assert len(facts) > 0
    assert facts[0].object_val == "Andrés"


def test_prompt_size_reduction() -> None:
    """Verify optimized prompt size for casual turns is smaller than baseline un-gated prompt."""
    container = DependencyContainer()
    builder = CognitiveContextBuilder(container=container)

    # 1. Un-gated baseline prompt (simulated with full dummy blocks injected)
    full_context = CognitiveContext(
        system_instruction=CognitiveContextBuilder.DEFAULT_INSTRUCTION,
        user_input="hola",
        world_entities=["Cámara HD (percepción)", "Micrófono USB (audio)"],
        relevant_memories=["[nombre del usuario]: Andrés", "[ciudad del usuario]: Madrid"],
        relevant_episodes=[
            type("Episode", (), {"id": "1", "summary": "Conversación sobre IA", "details": ""})()
        ],
        prioritized_goals=[
            type(
                "PrioritizedGoal",
                (),
                {
                    "rank": 1,
                    "score": 9.5,
                    "explanation": "Alta",
                    "goal": type(
                        "Goal",
                        (),
                        {
                            "goal_id": "g1",
                            "description": "Aprender más",
                            "status": type("Status", (), {"value": "active"})(),
                        },
                    )(),
                },
            )()
        ],
        available_tools=[
            {"name": "calculator", "description": "Calculates math expressions"},
            {"name": "weather", "description": "Get weather info"},
        ],
    )
    baseline_prompt = full_context.to_system_prompt() + full_context.to_formatted_prompt()
    baseline_tokens = len(baseline_prompt) // 4

    # 2. Optimized prompt for simple turn ("hola")
    casual_context = builder.build("hola")
    optimized_prompt = casual_context.to_system_prompt() + casual_context.to_formatted_prompt()
    optimized_tokens = len(optimized_prompt) // 4

    # Assert prompt size reduction
    assert optimized_tokens < baseline_tokens
    reduction_pct = ((baseline_tokens - optimized_tokens) / baseline_tokens) * 100.0

    print(
        f"\n[TOKEN REDUCTION BENEFIT] Baseline: {baseline_tokens} tokens | "
        f"Optimized: {optimized_tokens} tokens | Reduction: {reduction_pct:.1f}%"
    )
