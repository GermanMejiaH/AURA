from __future__ import annotations

import threading
from typing import Any

from ..events import EventBus
from .conversational import ConversationalMemory, ConversationTurn
from .episodic import EpisodicMemory
from .models import Episode
from .retrieval import MemoryRetriever
from .session import PersistentSessionManager
from .store import SQLiteMemoryStore


class CognitiveContextManager:
    """High-level facade providing persistent conversational & episodic context."""

    def __init__(
        self,
        memory: ConversationalMemory | None = None,
        session_manager: PersistentSessionManager | None = None,
        episodic_memory: EpisodicMemory | None = None,
        retriever: MemoryRetriever | None = None,
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
        self.episodic_memory = (
            episodic_memory
            if episodic_memory is not None
            else EpisodicMemory(store=self.store, event_bus=event_bus)
        )
        self.retriever = retriever if retriever is not None else MemoryRetriever(store=self.store)
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

    def get_relevant_episodes(
        self,
        query: str | None = None,
        intent_type: str | None = None,
        tools: list[str] | None = None,
        limit: int = 5,
    ) -> list[Episode]:
        """Retrieves relevant consolidated episodes using MemoryRetriever."""
        with self._lock:
            if query or intent_type or tools:
                results = self.retriever.search(
                    query=query or "",
                    intent_type=intent_type,
                    tools=tools,
                    limit=limit,
                )
                return [r.episode for r in results]
            return self.episodic_memory.all_episodes()[:limit]

    def build_cognitive_context(
        self, limit: int = 10, include_episodes: bool = True, limit_episodes: int = 3
    ) -> dict[str, Any]:
        """Builds structured context, wrapping memory as PASSIVE DATA (<retrieved_memory>)."""
        with self._lock:
            turns = self.get_recent_turns(limit=limit)
            episodes = self.get_relevant_episodes(limit=limit_episodes) if include_episodes else []

            formatted_lines: list[str] = ["<retrieved_memory>"]
            if turns:
                formatted_lines.append("[HISTORIAL CONVERSACIONAL]")
                for t in turns:
                    clean_content = t.content.replace(
                        "</retrieved_memory>", "[/retrieved_memory_escaped]"
                    )
                    clean_content = clean_content.replace(
                        "<retrieved_memory>", "[retrieved_memory_escaped]"
                    )
                    formatted_lines.append(f"[{t.role}]: {clean_content}")

            if episodes:
                formatted_lines.append("\n[EXPERIENCIAS EPISÓDICAS RELEVANTES]")
                for ep in episodes:
                    clean_summary = ep.summary.replace(
                        "</retrieved_memory>", "[/retrieved_memory_escaped]"
                    )
                    clean_summary = clean_summary.replace(
                        "<retrieved_memory>", "[retrieved_memory_escaped]"
                    )
                    formatted_lines.append(f"[episodio {ep.id}]: {clean_summary}")

            formatted_lines.append("</retrieved_memory>")
            formatted_block = "\n".join(formatted_lines)

            return {
                "session_id": self.session_manager.get_or_create_active_session().session_id,
                "turns_count": len(turns),
                "episodes_count": len(episodes),
                "history_turns": [{"role": t.role, "content": t.content} for t in turns],
                "episodes": [{"id": ep.id, "summary": ep.summary} for ep in episodes],
                "formatted_memory_block": formatted_block,
            }
