from __future__ import annotations

import threading
from uuid import uuid4

from ..events import EventBus
from .conversational import ConversationalMemory, SessionInfo
from .store import SQLiteMemoryStore


class PersistentSessionManager:
    """Manages active session context and lifecycle backed by SQLite ConversationalMemory."""

    def __init__(
        self,
        memory: ConversationalMemory | None = None,
        store: SQLiteMemoryStore | None = None,
        db_path: str = "data/aura.db",
        event_bus: EventBus | None = None,
    ) -> None:
        if memory is not None:
            self.memory = memory
        else:
            self.memory = ConversationalMemory(store=store, db_path=db_path, event_bus=event_bus)
        self._lock = threading.RLock()
        self._active_session_id: str | None = None

    def generate_session_id(self) -> str:
        """Generates a secure, deterministic session ID string format ('sess_<hex>')."""
        return f"sess_{uuid4().hex[:8]}"

    def create_session(
        self,
        session_id: str | None = None,
        title: str = "Conversación",
        user_id: str = "default_user",
    ) -> SessionInfo:
        """Creates a new session and sets it as the active session."""
        s_id = session_id if session_id else self.generate_session_id()
        with self._lock:
            info = self.memory.create_session(session_id=s_id, title=title, user_id=user_id)
            self._active_session_id = s_id
            return info

    def get_session(self, session_id: str) -> SessionInfo | None:
        """Gets session Info for a given session ID."""
        with self._lock:
            return self.memory.get_session(session_id)

    def get_active_session_id(self) -> str | None:
        """Returns the currently active session ID."""
        with self._lock:
            return self._active_session_id

    def set_active_session_id(self, session_id: str) -> bool:
        """Sets active session if session exists."""
        with self._lock:
            if self.memory.session_exists(session_id):
                self._active_session_id = session_id
                return True
            return False

    def get_or_create_active_session(self) -> SessionInfo:
        """Returns active session or creates a new default active session."""
        with self._lock:
            if self._active_session_id and self.memory.session_exists(self._active_session_id):
                sess = self.memory.get_session(self._active_session_id)
                if sess is not None:
                    return sess

            # Auto-create active session if none exists
            return self.create_session()

    def close_session(self, session_id: str) -> bool:
        """Closes and deletes a session and clears active ID if matched."""
        with self._lock:
            deleted = self.memory.delete_session(session_id)
            if deleted and self._active_session_id == session_id:
                self._active_session_id = None
            return deleted
