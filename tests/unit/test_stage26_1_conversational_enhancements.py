"""Unit tests for Stage 26.1 Conversational Context System Enhancements.

Validates:
1. Boot Hydration of WorkingMemory from conversation_turns table in SQLiteMemoryStore.
2. CognitiveContextBuilder intent reuse without redundant IntentDetector calls.
3. Integration with CognitionModule during initialization.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from aura.cognition.context import CognitiveContextBuilder
from aura.cognition.intent import Intent, IntentType
from aura.cognition.module import CognitionModule
from aura.cognition.working_memory import WorkingMemory
from aura.container import DependencyContainer
from aura.memory.conversational import ConversationalMemory
from aura.memory.store import SQLiteMemoryStore


@pytest.fixture
def memory_store() -> SQLiteMemoryStore:
    return SQLiteMemoryStore(":memory:")


class TestStage261ConversationalEnhancements:
    def test_working_memory_boot_hydration(self, memory_store: SQLiteMemoryStore) -> None:
        """Verify WorkingMemory hydrates past conversation turns from SQLite database on boot."""
        # 1. Pre-populate SQLite memory store with past turns
        conv_mem = ConversationalMemory(store=memory_store)
        conv_mem.add_turn(
            session_id="session-42",
            role="user",
            content="Mi nombre es Andrés",
            intent_type="identity_introduction",
        )
        conv_mem.add_turn(
            session_id="session-42",
            role="assistant",
            content="Hola Andrés, ¿en qué puedo ayudarte?",
        )
        conv_mem.add_turn(
            session_id="session-42",
            role="user",
            content="¿Cuál es la capital de Francia?",
            intent_type="factual_query",
        )
        conv_mem.add_turn(
            session_id="session-42",
            role="assistant",
            content="La capital de Francia es París.",
        )

        # 2. Instantiate WorkingMemory and hydrate
        wm = WorkingMemory()
        hydrated_count = wm.hydrate_from_db(store=memory_store, session_id="session-42", limit=10)

        # 3. Assert turns were restored into volatile WorkingMemory in correct chronological order
        assert hydrated_count == 4
        recent_turns = wm.get_recent_conversation(limit=10)
        assert len(recent_turns) == 4

        assert recent_turns[0]["role"] == "user"
        assert recent_turns[0]["content"] == "Mi nombre es Andrés"

        assert recent_turns[1]["role"] == "assistant"
        assert recent_turns[1]["content"] == "Hola Andrés, ¿en qué puedo ayudarte?"

        assert recent_turns[2]["role"] == "user"
        assert recent_turns[2]["content"] == "¿Cuál es la capital de Francia?"

        assert recent_turns[3]["role"] == "assistant"
        assert recent_turns[3]["content"] == "La capital de Francia es París."

    def test_working_memory_boot_hydration_empty_db(self, memory_store: SQLiteMemoryStore) -> None:
        """Verify hydration gracefully handles empty database sessions."""
        wm = WorkingMemory()
        hydrated_count = wm.hydrate_from_db(store=memory_store, session_id="non-existent-session")
        assert hydrated_count == 0
        assert len(wm.get_recent_conversation()) == 0

    def test_cognitive_context_builder_intent_reuse(self) -> None:
        """Verify CognitiveContextBuilder reuses passed intent without re-calling IntentDetector."""
        builder = CognitiveContextBuilder()
        pre_detected_intent = Intent(
            intent_type=IntentType.QUESTION,
            confidence=0.95,
            parameters={"query": "name"},
            raw_text="¿Cómo me llamo?",
        )

        with patch("aura.cognition.intent.IntentDetector.detect") as mock_detect:
            ctx = builder.build(
                input_text="¿Cómo me llamo?",
                intent=pre_detected_intent,
            )
            # IntentDetector.detect should NOT be called when intent is passed
            mock_detect.assert_not_called()
            assert ctx.intent == pre_detected_intent

    def test_cognition_module_boot_hydration_integration(
        self, memory_store: SQLiteMemoryStore
    ) -> None:
        """Verify CognitionModule hydrates WorkingMemory on initialization
        when container is provided."""
        # 1. Store turn in DB
        conv_mem = ConversationalMemory(store=memory_store)
        conv_mem.add_turn(
            session_id="session-default",
            role="user",
            content="Tengo un gato llamado Misi",
        )
        conv_mem.add_turn(
            session_id="session-default",
            role="assistant",
            content="¡Qué bonito nombre!",
        )

        # 2. Setup Container
        container = DependencyContainer()
        container.register(SQLiteMemoryStore, instance=memory_store)

        # 3. Instantiate CognitionModule with container
        cognition = CognitionModule(container=container)
        cognition.on_initialize()

        # 4. Verify WorkingMemory in cognition module was hydrated
        turns = cognition.working_memory.get_recent_conversation()
        assert len(turns) == 2
        assert turns[0]["content"] == "Tengo un gato llamado Misi"
        assert turns[1]["content"] == "¡Qué bonito nombre!"
