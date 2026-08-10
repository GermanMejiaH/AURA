from __future__ import annotations

import json
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from ..logging import get_logger
from .models import Episode, Fact, Preference


class MemoryStore(ABC):
    """Abstract persistent storage engine interface for AURA long-term memory."""

    @abstractmethod
    def save_fact(self, fact: Fact) -> None: ...

    @abstractmethod
    def get_facts(
        self, subject: str | None = None, predicate: str | None = None
    ) -> list[Fact]: ...

    @abstractmethod
    def delete_fact(self, fact_id: str) -> bool: ...

    @abstractmethod
    def save_episode(self, episode: Episode) -> None: ...

    @abstractmethod
    def get_episodes(self, query: str | None = None, limit: int = 5) -> list[Episode]: ...

    @abstractmethod
    def save_preference(self, pref: Preference) -> None: ...

    @abstractmethod
    def get_preference(self, key: str) -> Preference | None: ...

    @abstractmethod
    def get_all_preferences(self) -> list[Preference]: ...

    @abstractmethod
    def close(self) -> None: ...


class SQLiteMemoryStore(MemoryStore):
    """Thread-safe SQLite persistent store for Fact, Episode, and Preference records."""

    def __init__(self, db_path: str = "data/aura.db") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                dir_name = os.path.dirname(self.db_path)
                if dir_name and not os.path.exists(dir_name):
                    os.makedirs(dir_name, exist_ok=True)
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
            return self._conn

    def _init_db(self) -> None:
        logger = get_logger("SQLiteMemoryStore")
        try:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS facts (
                        id TEXT PRIMARY KEY,
                        subject TEXT NOT NULL,
                        predicate TEXT NOT NULL,
                        object_val TEXT NOT NULL,
                        confidence REAL NOT NULL DEFAULT 1.0,
                        source TEXT NOT NULL DEFAULT 'user',
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS episodes (
                        id TEXT PRIMARY KEY,
                        summary TEXT NOT NULL,
                        details TEXT NOT NULL DEFAULT '',
                        timestamp TEXT NOT NULL,
                        tags TEXT NOT NULL DEFAULT '[]',
                        importance REAL NOT NULL DEFAULT 1.0
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS preferences (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT 'general',
                        updated_at TEXT NOT NULL
                    )
                    """
                )
            logger.info(f"SQLiteMemoryStore initialized at '{self.db_path}'")
        except Exception as exc:
            logger.error(f"Failed to initialize SQLite database '{self.db_path}': {exc}")

    def save_fact(self, fact: Fact) -> None:
        with self._lock:
            try:
                conn = self._get_connection()
                iso_created = (
                    fact.created_at.isoformat()
                    if isinstance(fact.created_at, datetime)
                    else str(fact.created_at)
                )
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO facts
                        (id, subject, predicate, object_val, confidence, source, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            fact.id,
                            fact.subject,
                            fact.predicate,
                            fact.object_val,
                            fact.confidence,
                            fact.source,
                            iso_created,
                        ),
                    )
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Error saving fact '{fact.id}': {exc}")

    def get_facts(
        self, subject: str | None = None, predicate: str | None = None
    ) -> list[Fact]:
        with self._lock:
            try:
                conn = self._get_connection()
                query = (
                    "SELECT id, subject, predicate, object_val, confidence, source, created_at "
                    "FROM facts"
                )
                params: list[Any] = []
                where_clauses: list[str] = []

                if subject is not None:
                    where_clauses.append("LOWER(subject) LIKE ?")
                    params.append(f"%{subject.lower()}%")
                if predicate is not None:
                    where_clauses.append("LOWER(predicate) LIKE ?")
                    params.append(f"%{predicate.lower()}%")

                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)

                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                facts: list[Fact] = []
                for r in rows:
                    dt = self._parse_iso(r["created_at"])
                    facts.append(
                        Fact(
                            id=r["id"],
                            subject=r["subject"],
                            predicate=r["predicate"],
                            object_val=r["object_val"],
                            confidence=float(r["confidence"]),
                            source=r["source"],
                            created_at=dt,
                        )
                    )
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Error querying facts: {exc}")
                return []
            else:
                return facts

    def delete_fact(self, fact_id: str) -> bool:
        with self._lock:
            try:
                conn = self._get_connection()
                with conn:
                    cur = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
                    return cur.rowcount > 0
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Error deleting fact '{fact_id}': {exc}")
                return False

    def save_episode(self, episode: Episode) -> None:
        with self._lock:
            try:
                conn = self._get_connection()
                iso_ts = (
                    episode.timestamp.isoformat()
                    if isinstance(episode.timestamp, datetime)
                    else str(episode.timestamp)
                )
                tags_json = json.dumps(episode.tags)
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO episodes
                        (id, summary, details, timestamp, tags, importance)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            episode.id,
                            episode.summary,
                            episode.details,
                            iso_ts,
                            tags_json,
                            episode.importance,
                        ),
                    )
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Error saving episode '{episode.id}': {exc}")

    def get_episodes(self, query: str | None = None, limit: int = 5) -> list[Episode]:
        with self._lock:
            try:
                conn = self._get_connection()
                sql = "SELECT id, summary, details, timestamp, tags, importance FROM episodes"
                params: list[Any] = []
                if query:
                    sql += " WHERE LOWER(summary) LIKE ? OR LOWER(details) LIKE ?"
                    params.extend([f"%{query.lower()}%", f"%{query.lower()}%"])
                sql += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()
                episodes: list[Episode] = []
                for r in rows:
                    dt = self._parse_iso(r["timestamp"])
                    try:
                        tags_list = json.loads(r["tags"])
                    except Exception:
                        tags_list = []
                    episodes.append(
                        Episode(
                            id=r["id"],
                            summary=r["summary"],
                            details=r["details"],
                            timestamp=dt,
                            tags=tags_list,
                            importance=float(r["importance"]),
                        )
                    )
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Error querying episodes: {exc}")
                return []
            else:
                return episodes

    def save_preference(self, pref: Preference) -> None:
        with self._lock:
            try:
                conn = self._get_connection()
                iso_upd = (
                    pref.updated_at.isoformat()
                    if isinstance(pref.updated_at, datetime)
                    else str(pref.updated_at)
                )
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO preferences
                        (key, value, category, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (pref.key, pref.value, pref.category, iso_upd),
                    )
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Error saving preference '{pref.key}': {exc}")

    def get_preference(self, key: str) -> Preference | None:
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.execute(
                    "SELECT key, value, category, updated_at FROM preferences WHERE key = ?",
                    (key,),
                )
                row = cursor.fetchone()
                found_pref = (
                    Preference(
                        key=row["key"],
                        value=row["value"],
                        category=row["category"],
                        updated_at=self._parse_iso(row["updated_at"]),
                    )
                    if row
                    else None
                )
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Error reading preference '{key}': {exc}")
                return None
            else:
                return found_pref

    def get_all_preferences(self) -> list[Preference]:
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.execute("SELECT key, value, category, updated_at FROM preferences")
                rows = cursor.fetchall()
                prefs: list[Preference] = []
                for r in rows:
                    dt = self._parse_iso(r["updated_at"])
                    prefs.append(
                        Preference(
                            key=r["key"],
                            value=r["value"],
                            category=r["category"],
                            updated_at=dt,
                        )
                    )
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Error listing preferences: {exc}")
                return []
            else:
                return prefs

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    @staticmethod
    def _parse_iso(iso_str: str) -> datetime:
        try:
            return datetime.fromisoformat(iso_str)
        except Exception:
            from datetime import UTC
            return datetime.now(UTC)
