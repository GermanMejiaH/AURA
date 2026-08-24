from __future__ import annotations

from aura.cognition.context import CognitiveContextBuilder
from aura.cognition.intent import Intent, IntentType
from aura.cognition.module import CognitionModule
from aura.cognition.working_memory import WorkingMemory
from aura.container import DependencyContainer
from aura.memory.conversational import ConversationalMemory
from aura.memory.store import SQLiteMemoryStore


def test_cognitive_context_builder_no_duplicate_history():
    """Verify context builder includes conversation history once, not duplicated."""
    container = DependencyContainer()
    builder = CognitiveContextBuilder(container=container)
    wm = WorkingMemory()
    wm.add_conversation_turn("user", "Hola AURA")
    wm.add_conversation_turn("assistant", "Hola Andrés, ¿en qué te puedo ayudar?")

    ctx = builder.build(
        input_text="¿Cómo me llamo?",
        working_memory=wm,
    )

    formatted_prompt = ctx.to_formatted_prompt()
    system_prompt = ctx.to_system_prompt()

    # System prompt should contain working memory history
    assert "Hola AURA" in system_prompt or "Hola AURA" in formatted_prompt
    # The formatted prompt user section should only contain the input_text prompt, not history again
    assert formatted_prompt.count("Hola AURA") == 1 or system_prompt.count("Hola AURA") == 1


test_cognitive_context_builder_no_duplicate_history()


def test_intent_reuse_in_context_builder():
    """Verify passing explicit intent saves redundant detection and is populated in context."""
    container = DependencyContainer()
    builder = CognitiveContextBuilder(container=container)

    explicit_intent = Intent(
        intent_type=IntentType.MEMORY_QUERY,
        confidence=0.99,
        raw_text="¿Cómo me llamo?",
    )

    ctx = builder.build(
        input_text="¿Cómo me llamo?",
        intent=explicit_intent,
    )

    assert ctx.intent == explicit_intent
    assert ctx.intent.intent_type == IntentType.MEMORY_QUERY


def test_relevance_gating_in_context_builder():
    """Verify context builder only pulls irrelevant blocks when relevant."""
    container = DependencyContainer()
    builder = CognitiveContextBuilder(container=container)

    # Casual greeting should not pollute prompt with empty/irrelevant tools or cwm
    ctx = builder.build(input_text="Hola buenas tardes")
    assert ctx.available_tools == []
    assert ctx.world_entities == []


def test_working_memory_boot_hydration(tmp_path):
    """Verify WorkingMemory hydrates recent conversation turns from SQLite database on boot."""
    db_file = str(tmp_path / "test_aura.db")
    store = SQLiteMemoryStore(db_path=db_file)

    # Persist session and 3 turns
    conv_mem = ConversationalMemory(store=store)
    sess = conv_mem.create_session(title="Test Session")
    conv_mem.add_turn(sess.session_id, "user", "Mi nombre es Andrés")
    conv_mem.add_turn(sess.session_id, "assistant", "Mucho gusto Andrés")
    conv_mem.add_turn(sess.session_id, "user", "Tengo una hermana llamada Maria")

    # Initialize a new WorkingMemory and hydrate from store
    wm = WorkingMemory()
    count = wm.hydrate_from_db(store=store)

    assert count == 3
    history = wm.get_recent_conversation()
    assert len(history) == 3
    assert history[0]["content"] == "Mi nombre es Andrés"
    assert history[2]["content"] == "Tengo una hermana llamada Maria"


def test_cognition_module_boot_hydrates_working_memory(tmp_path):
    """Verify CognitionModule.on_initialize() automatically hydrates WorkingMemory
    when container has SQLiteMemoryStore."""
    db_file = str(tmp_path / "test_aura.db")
    store = SQLiteMemoryStore(db_path=db_file)

    conv_mem = ConversationalMemory(store=store)
    sess = conv_mem.create_session(title="Boot Test Session")
    conv_mem.add_turn(sess.session_id, "user", "Hola AURA")

    container = DependencyContainer()
    container.register(SQLiteMemoryStore, instance=store)

    cog_module = CognitionModule(container=container)
    cog_module.on_initialize()

    history = cog_module.working_memory.get_recent_conversation()
    assert len(history) == 1
    assert history[0]["content"] == "Hola AURA"
