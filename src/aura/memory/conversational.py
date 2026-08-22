from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ..events import ConversationTurnStored, EventBus, SessionClosed, SessionCreated
from ..logging import get_logger
from .store import SQLiteMemoryStore


def _utcnow() -> datetime:
    return datetime.now(UTC)


VALID_ROLES = {"user", "assistant", "system"}


@dataclass
class SessionInfo:
    session_id: str
    title: str = "Conversación"
    user_id: str = "default_user"
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass
class ConversationTurn:
    session_id: str
    role: str
    content: str
    turn_id: str = field(default_factory=lambda: str(uuid4()))
    intent_type: str | None = None
    timestamp: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class ConversationalMemory:
    """Thread-safe persistent store for conversation sessions and turns in SQLite."""

    def __init__(
        self,
        store: SQLiteMemoryStore | None = None,
        db_path: str = "data/aura.db",
        event_bus: EventBus | None = None,
        container: Any | None = None,
    ) -> None:
        if store is not None:
            self.store = store
        elif (
            container is not None and hasattr(container, "has") and container.has(SQLiteMemoryStore)
        ):
            self.store = container.resolve(SQLiteMemoryStore)
        elif container is not None and hasattr(container, "has") and container.has("MemoryStore"):
            self.store = container.resolve("MemoryStore")
        else:
            self.store = SQLiteMemoryStore(db_path=db_path)

        self._lock = self.store._lock
        self.event_bus = event_bus

    def create_session(
        self,
        session_id: str | None = None,
        title: str = "Conversación",
        user_id: str = "default_user",
    ) -> SessionInfo:
        """Creates or updates a conversation session in SQLite."""
        logger = get_logger("ConversationalMemory")
        s_id = session_id if session_id else f"sess_{uuid4().hex[:8]}"
        now = _utcnow()
        sess = SessionInfo(
            session_id=s_id,
            title=title,
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            try:
                conn = self.store._get_connection()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO memory_sessions (
                            session_id, user_id, title, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?)

                        ON CONFLICT(session_id) DO UPDATE SET
                            title = excluded.title,
                            updated_at = excluded.updated_at
                        """,
                        (s_id, user_id, title, now.isoformat(), now.isoformat()),
                    )
            except Exception as exc:
                logger.error(f"Failed to create session '{s_id}': {exc}")

        if self.event_bus is not None:
            self.event_bus.publish(
                SessionCreated(
                    source="ConversationalMemory",
                    session_id=s_id,
                    title=title,
                    user_id=user_id,
                )
            )

        return sess

    def get_session(self, session_id: str) -> SessionInfo | None:
        """Retrieves session metadata if it exists."""
        logger = get_logger("ConversationalMemory")
        with self._lock:
            try:
                conn = self.store._get_connection()
                cur = conn.execute(
                    """
                    SELECT session_id, user_id, title, created_at, updated_at
                    FROM memory_sessions WHERE session_id = ?
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return SessionInfo(
                    session_id=row["session_id"],
                    user_id=row["user_id"],
                    title=row["title"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
            except Exception as exc:
                logger.error(f"Failed to get session '{session_id}': {exc}")
                return None

    def session_exists(self, session_id: str) -> bool:
        """Checks if a session ID exists in SQLite."""
        return self.get_session(session_id) is not None

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session and all its cascading conversation turns."""
        logger = get_logger("ConversationalMemory")
        with self._lock:
            try:
                conn = self.store._get_connection()
                with conn:
                    cur = conn.execute(
                        "DELETE FROM memory_sessions WHERE session_id = ?",
                        (session_id,),
                    )
                    deleted = cur.rowcount > 0
            except Exception as exc:
                logger.error(f"Failed to delete session '{session_id}': {exc}")
                return False

        if deleted and self.event_bus is not None:
            self.event_bus.publish(
                SessionClosed(
                    source="ConversationalMemory",
                    session_id=session_id,
                )
            )

        return deleted

    def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        intent_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationTurn:
        """Persists a conversation turn into SQLite after validating the role."""
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{role}'. Expected one of {sorted(VALID_ROLES)}.")

        if not self.session_exists(session_id):
            self.create_session(session_id=session_id)

        now = _utcnow()
        turn = ConversationTurn(
            session_id=session_id,
            role=role,
            content=content,
            intent_type=intent_type,
            timestamp=now,
            metadata=metadata or {},
        )

        logger = get_logger("ConversationalMemory")
        meta_json = json.dumps(turn.metadata)

        with self._lock:
            try:
                conn = self.store._get_connection()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO conversation_turns
                        (turn_id, session_id, role, content, intent_type, timestamp, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            turn.turn_id,
                            session_id,
                            role,
                            content,
                            intent_type,
                            now.isoformat(),
                            meta_json,
                        ),
                    )
                    conn.execute(
                        "UPDATE memory_sessions SET updated_at = ? WHERE session_id = ?",
                        (now.isoformat(), session_id),
                    )
            except Exception as exc:
                logger.error(f"Failed to add turn for session '{session_id}': {exc}")

        if self.event_bus is not None:
            self.event_bus.publish(
                ConversationTurnStored(
                    source="ConversationalMemory",
                    session_id=session_id,
                    turn_id=turn.turn_id,
                    role=role,
                )
            )

        return turn

    def get_session_turns(
        self, session_id: str, limit: int | None = None
    ) -> list[ConversationTurn]:
        """Retrieves turns for a session ordered chronologically."""
        logger = get_logger("ConversationalMemory")
        with self._lock:
            try:
                conn = self.store._get_connection()
                sql = """
                    SELECT turn_id, session_id, role, content, intent_type, timestamp, metadata_json
                    FROM conversation_turns
                    WHERE session_id = ?
                    ORDER BY timestamp ASC, turn_id ASC
                """
                params: list[Any] = [session_id]
                cur = conn.execute(sql, params)
                rows = cur.fetchall()

                turns: list[ConversationTurn] = []
                for r in rows:
                    try:
                        meta = json.loads(r["metadata_json"])
                    except Exception:
                        meta = {}
                    turns.append(
                        ConversationTurn(
                            turn_id=r["turn_id"],
                            session_id=r["session_id"],
                            role=r["role"],
                            content=r["content"],
                            intent_type=r["intent_type"],
                            timestamp=datetime.fromisoformat(r["timestamp"]),
                            metadata=meta,
                        )
                    )
            except Exception as exc:
                logger.error(f"Failed to get turns for session '{session_id}': {exc}")
                return []
            else:
                if limit is not None and len(turns) > limit:
                    turns = turns[-limit:]
                return turns

    def get_recent_turns(self, session_id: str, limit: int = 10) -> list[ConversationTurn]:
        """Convenience method to retrieve recent N turns in chronological order."""
        return self.get_session_turns(session_id=session_id, limit=limit)
