from __future__ import annotations

import threading
from typing import Any

from ..events import EventBus
from .conversational import ConversationalMemory, ConversationTurn
from .session import PersistentSessionManager
from .store import SQLiteMemoryStore


class CognitiveContextManager:
    """High-level facade providing persistent conversational context for CognitionModule."""

    def __init__(
        self,
        memory: ConversationalMemory | None = None,
        session_manager: PersistentSessionManager | None = None,
        store: SQLiteMemoryStore | None = None,
        db_path: str = "data/aura.db",
        event_bus: EventBus | None = None,
    ) -> None:
        self.store = store if store is not None else SQLiteMemoryStore(db_path=db_path)
        self.memory = (
            memory
            if memory is not None
            else ConversationalMemory(store=self.store, event_bus=event_bus)
        )
        self.session_manager = (
            session_manager
            if session_manager is not None
            else PersistentSessionManager(memory=self.memory, event_bus=event_bus)
        )
        self._lock = threading.RLock()

    def get_or_create_session(self) -> str:
        """Returns the active session ID or creates a new active session."""
        with self._lock:
            sess = self.session_manager.get_or_create_active_session()
            return sess.session_id

    def add_user_turn(
        self, content: str, intent_type: str | None = None, metadata: dict[str, Any] | None = None
    ) -> ConversationTurn:
        """Persists a user turn for the active session."""
        with self._lock:
            s_id = self.session_manager.get_or_create_active_session().session_id
            return self.memory.add_turn(
                session_id=s_id,
                role="user",
                content=content,
                intent_type=intent_type,
                metadata=metadata,
            )

    def add_assistant_turn(
        self, content: str, metadata: dict[str, Any] | None = None
    ) -> ConversationTurn:
        """Persists an assistant response turn for the active session."""
        with self._lock:
            s_id = self.session_manager.get_or_create_active_session().session_id
            return self.memory.add_turn(
                session_id=s_id,
                role="assistant",
                content=content,
                metadata=metadata,
            )

    def add_system_turn(
        self, content: str, metadata: dict[str, Any] | None = None
    ) -> ConversationTurn:
        """Persists a system context turn for the active session."""
        with self._lock:
            s_id = self.session_manager.get_or_create_active_session().session_id
            return self.memory.add_turn(
                session_id=s_id,
                role="system",
                content=content,
                metadata=metadata,
            )

    def get_recent_turns(self, limit: int = 10) -> list[ConversationTurn]:
        """Retrieves recent N turns for the active session in chronological order."""
        with self._lock:
            s_id = self.session_manager.get_or_create_active_session().session_id
            return self.memory.get_recent_turns(session_id=s_id, limit=limit)

    def build_cognitive_context(self, limit: int = 10) -> dict[str, Any]:
        """Builds structured context, wrapping memory as PASSIVE DATA (<retrieved_memory>)."""
        turns = self.get_recent_turns(limit=limit)

        formatted_lines: list[str] = ["<retrieved_memory>"]
        for t in turns:
            formatted_lines.append(f"[{t.role}]: {t.content}")
        formatted_lines.append("</retrieved_memory>")

        formatted_block = "\n".join(formatted_lines)

        return {
            "session_id": self.session_manager.get_or_create_active_session().session_id,
            "turns_count": len(turns),
            "history_turns": [{"role": t.role, "content": t.content} for t in turns],
            "formatted_memory_block": formatted_block,
        }
