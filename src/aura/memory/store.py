"""Memory Store Implementation — AURA 1.6 Stage 24.

Provides abstract MemoryStore interface and thread-safe SQLiteMemoryStore with
versioned schema migrations via PRAGMA user_version.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from aura.logging import get_logger
from aura.memory.models import Episode, Fact, Preference

CURRENT_SCHEMA_VERSION = 1


class MemoryStore(ABC):
    """Abstract base class for long-term memory stores."""

    @abstractmethod
    def save_fact(self, fact: Fact) -> None:
        pass

    @abstractmethod
    def get_facts(self, subject: str | None = None, predicate: str | None = None) -> list[Fact]:
        pass

    @abstractmethod
    def delete_fact(self, fact_id: str) -> bool:
        pass

    @abstractmethod
    def save_preference(self, preference: Preference) -> None:
        pass

    @abstractmethod
    def get_preference(self, key: str) -> Preference | None:
        pass

    @abstractmethod
    def get_preferences(self) -> list[Preference]:
        pass

    @abstractmethod
    def get_all_preferences(self) -> list[Preference]:
        pass

    @abstractmethod
    def delete_preference(self, key: str) -> bool:
        pass

    @abstractmethod
    def save_episode(self, episode: Episode) -> None:
        pass

    @abstractmethod
    def get_episodes(self, limit: int = 50, query: str | None = None) -> list[Episode]:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class SQLiteMemoryStore(MemoryStore):
    """SQLite-backed implementation of MemoryStore supporting facts, episodes, and preferences.

    Thread-safe implementation with versioned schema migrations via PRAGMA user_version.
    """

    def __init__(self, db_path: str = "data/aura.db") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                dir_name = os.path.dirname(self.db_path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA foreign_keys = ON;")
                if self.db_path != ":memory:":
                    self._conn.execute("PRAGMA journal_mode = WAL;")
                self._conn.execute("PRAGMA busy_timeout = 5000;")
            return self._conn

    def _init_db(self) -> None:
        logger = get_logger("SQLiteMemoryStore")
        try:
            conn = self._get_connection()
            # 1. Versioned Schema Migrations
            self._run_migrations(conn)

            # 2. DDL Table Initialization for current schema
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS facts (
                        id TEXT PRIMARY KEY,
                        subject TEXT NOT NULL,
                        predicate TEXT NOT NULL,
                        object TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        source TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS episodes (
                        id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        event_type TEXT NOT NULL DEFAULT 'episode',
                        summary TEXT NOT NULL,
                        payload TEXT NOT NULL DEFAULT '{}',
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
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_plans (
                        plan_id TEXT PRIMARY KEY,
                        goal_id TEXT NOT NULL,
                        goal_description TEXT NOT NULL,
                        status TEXT NOT NULL,
                        replan_count INTEGER NOT NULL DEFAULT 0,
                        max_replans INTEGER NOT NULL DEFAULT 2,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                try:
                    conn.execute(
                        "ALTER TABLE agent_plans ADD COLUMN replan_count "
                        "INTEGER NOT NULL DEFAULT 0;"
                    )
                except Exception:
                    pass

                try:
                    conn.execute(
                        "ALTER TABLE agent_plans ADD COLUMN max_replans INTEGER NOT NULL DEFAULT 2;"
                    )
                except Exception:
                    pass

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_tasks (
                        task_id TEXT PRIMARY KEY,
                        plan_id TEXT NOT NULL,
                        task_order INTEGER NOT NULL,
                        description TEXT NOT NULL,
                        status TEXT NOT NULL,
                        tool_name TEXT,
                        parameters_json TEXT NOT NULL DEFAULT '{}',
                        result_json TEXT,
                        error TEXT,
                        FOREIGN KEY (plan_id) REFERENCES agent_plans(plan_id) ON DELETE CASCADE
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL DEFAULT 'default_user',
                        title TEXT NOT NULL DEFAULT 'Conversación',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversation_turns (
                        turn_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        intent_type TEXT,
                        timestamp TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        FOREIGN KEY (session_id)
                        REFERENCES memory_sessions(session_id) ON DELETE CASCADE
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_conversation_turns_session_timestamp
                    ON conversation_turns(session_id, timestamp)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS proactive_tasks (
                        task_id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        creation_turn_id TEXT NOT NULL,
                        trigger_type TEXT NOT NULL,
                        trigger_definition_json TEXT NOT NULL,
                        action_proposal_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        next_evaluation_at TEXT,
                        last_evaluation_at TEXT,
                        execution_count INTEGER NOT NULL DEFAULT 0,
                        max_executions INTEGER NOT NULL DEFAULT 1,
                        expires_at TEXT,
                        correlation_id TEXT NOT NULL,
                        operation_id TEXT,
                        last_execution_id TEXT,
                        last_outcome_id TEXT,
                        cancellation_reason TEXT,
                        metadata_json TEXT NOT NULL DEFAULT '{}'
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_proactive_tasks_conv_status
                    ON proactive_tasks(conversation_id, status)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS proactive_task_executions (
                        execution_id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        operation_id TEXT NOT NULL,
                        executed_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        outcome_summary TEXT,
                        error TEXT,
                        FOREIGN KEY (task_id) REFERENCES proactive_tasks(task_id) ON DELETE CASCADE
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS proactive_notifications (
                        notification_id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        conversation_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        success INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        delivered INTEGER NOT NULL DEFAULT 0,
                        operation_id TEXT,
                        metadata_json TEXT NOT NULL DEFAULT '{}'
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_proactive_notifications_conv
                    ON proactive_notifications(conversation_id, delivered)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_facts_subject_predicate
                    ON facts(subject, predicate)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_episodes_timestamp
                    ON episodes(timestamp DESC)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_preferences_updated
                    ON preferences(updated_at DESC)
                    """
                )

            logger.info(f"SQLiteMemoryStore initialized at '{self.db_path}'")

        except Exception as exc:
            logger.error(f"Failed to initialize SQLite database '{self.db_path}': {exc}")
            raise

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        """Executes versioned schema migrations based on PRAGMA user_version."""
        logger = get_logger("SQLiteMemoryStore")
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        row = cursor.fetchone()
        current_version = row[0] if row else 0

        if current_version < 1:
            logger.info(f"Migrating SQLite database '{self.db_path}' from V{current_version} -> V1")
            old_isolation = conn.isolation_level
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE;")
            try:
                self._migrate_v0_to_v1(conn)
                conn.execute("PRAGMA user_version = 1;")
                conn.execute("COMMIT;")
            except Exception:
                conn.execute("ROLLBACK;")
                raise
            finally:
                conn.isolation_level = old_isolation
            logger.info(f"Database '{self.db_path}' migrated successfully to schema V1.")

    def _migrate_v0_to_v1(self, conn: sqlite3.Connection) -> None:
        """Executes V0 -> V1 schema migration for facts and episodes tables."""
        logger = get_logger("SQLiteMemoryStore")
        cursor = conn.cursor()

        # 1. Facts table migration: object_val -> object
        cursor.execute("PRAGMA table_info(facts);")
        facts_cols = {row["name"]: row for row in cursor.fetchall()}

        if facts_cols and "object_val" in facts_cols and "object" not in facts_cols:
            logger.info("Migrating table 'facts': renaming column 'object_val' -> 'object'")
            conn.execute("ALTER TABLE facts RENAME COLUMN object_val TO object;")

        # 2. Episodes table migration: add event_type, add payload, migrate details/tags
        cursor.execute("PRAGMA table_info(episodes);")
        episodes_cols = {row["name"]: row for row in cursor.fetchall()}

        if episodes_cols:
            if "event_type" not in episodes_cols:
                logger.info("Migrating table 'episodes': adding column 'event_type'")
                conn.execute(
                    "ALTER TABLE episodes ADD COLUMN event_type TEXT NOT NULL DEFAULT 'episode';"
                )

            if "payload" not in episodes_cols:
                logger.info("Migrating table 'episodes': adding column 'payload'")
                conn.execute("ALTER TABLE episodes ADD COLUMN payload TEXT NOT NULL DEFAULT '{}';")

                has_details = "details" in episodes_cols
                has_tags = "tags" in episodes_cols

                if has_details or has_tags:
                    logger.info("Migrating legacy details/tags into episode payload JSON...")
                    select_sql = "SELECT id"
                    if has_details:
                        select_sql += ", details"
                    if has_tags:
                        select_sql += ", tags"
                    select_sql += " FROM episodes;"

                    cursor.execute(select_sql)
                    legacy_rows = cursor.fetchall()

                    for row in legacy_rows:
                        ep_id = row["id"]
                        dt_val = (
                            row["details"] if has_details and row["details"] is not None else ""
                        )
                        tg_raw = row["tags"] if has_tags and row["tags"] is not None else "[]"

                        tg_val = []
                        if isinstance(tg_raw, str):
                            try:
                                tg_val = json.loads(tg_raw)
                            except Exception:
                                tg_val = [tg_raw] if tg_raw else []
                        elif isinstance(tg_raw, list):
                            tg_val = tg_raw

                        payload_str = json.dumps({"details": dt_val, "tags": tg_val})
                        conn.execute(
                            "UPDATE episodes SET payload = ? WHERE id = ?;",
                            (payload_str, ep_id),
                        )

    def save_fact(self, fact: Fact) -> None:
        import time

        from ..telemetry import TelemetryManager

        t0 = time.perf_counter()
        with self._lock:
            try:
                conn = self._get_connection()
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO facts
                        (id, subject, predicate, object, confidence, source, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            fact.id,
                            fact.subject,
                            fact.predicate,
                            fact.object_val,
                            fact.confidence,
                            fact.source,
                            fact.created_at.isoformat(),
                        ),
                    )
                telemetry = TelemetryManager.get_instance()
                telemetry.increment("memory_writes")
                telemetry.record_latency("time_memory_ms", (time.perf_counter() - t0) * 1000)
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Failed to save fact '{fact.id}': {exc}")

    def delete_fact(self, fact_id: str) -> bool:
        with self._lock:
            try:
                conn = self._get_connection()
                with conn:
                    cur = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Failed to delete fact '{fact_id}': {exc}")
                return False
            else:
                return cur.rowcount > 0

    def get_facts(self, subject: str | None = None, predicate: str | None = None) -> list[Fact]:
        import time

        from ..telemetry import TelemetryManager

        t0 = time.perf_counter()
        with self._lock:
            try:
                conn = self._get_connection()
                sql = "SELECT * FROM facts"
                params: list[Any] = []
                where_clauses: list[str] = []

                if subject is not None:
                    where_clauses.append("subject = ?")
                    params.append(subject)
                if predicate is not None:
                    where_clauses.append("predicate = ?")
                    params.append(predicate)

                if where_clauses:
                    sql += " WHERE " + " AND ".join(where_clauses)
                sql += " ORDER BY created_at DESC"

                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()
                facts: list[Fact] = []
                for row in rows:
                    facts.append(
                        Fact(
                            id=row["id"],
                            subject=row["subject"],
                            predicate=row["predicate"],
                            object_val=row["object"],
                            confidence=row["confidence"],
                            source=row["source"],
                        )
                    )
                telemetry = TelemetryManager.get_instance()
                telemetry.increment("memory_retrievals")
                telemetry.record_latency("time_memory_ms", (time.perf_counter() - t0) * 1000)
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Failed to retrieve facts: {exc}")
                return []
            else:
                return facts

    def save_preference(self, preference: Preference) -> None:
        import time

        from ..telemetry import TelemetryManager

        t0 = time.perf_counter()
        with self._lock:
            try:
                conn = self._get_connection()
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO preferences (key, value, category, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            preference.key,
                            preference.value,
                            preference.category,
                            preference.updated_at.isoformat(),
                        ),
                    )
                telemetry = TelemetryManager.get_instance()
                telemetry.increment("memory_writes")
                telemetry.record_latency("time_memory_ms", (time.perf_counter() - t0) * 1000)
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Failed to save preference '{preference.key}': {exc}")

    def get_preference(self, key: str) -> Preference | None:
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.execute("SELECT * FROM preferences WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row is None:
                    return None
                return Preference(
                    key=row["key"],
                    value=row["value"],
                    category=row["category"],
                )
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Failed to get preference '{key}': {exc}")
                return None

    def get_preferences(self) -> list[Preference]:
        return self.get_all_preferences()

    def get_all_preferences(self) -> list[Preference]:
        import time

        from ..telemetry import TelemetryManager

        t0 = time.perf_counter()
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.execute("SELECT * FROM preferences ORDER BY updated_at DESC")
                rows = cursor.fetchall()
                prefs: list[Preference] = []
                for row in rows:
                    prefs.append(
                        Preference(
                            key=row["key"],
                            value=row["value"],
                            category=row["category"],
                        )
                    )
                telemetry = TelemetryManager.get_instance()
                telemetry.increment("memory_retrievals")
                telemetry.record_latency("time_memory_ms", (time.perf_counter() - t0) * 1000)
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Failed to retrieve preferences: {exc}")
                return []
            else:
                return prefs

    def delete_preference(self, key: str) -> bool:
        with self._lock:
            try:
                conn = self._get_connection()
                with conn:
                    cur = conn.execute("DELETE FROM preferences WHERE key = ?", (key,))
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Failed to delete preference '{key}': {exc}")
                return False
            else:
                return cur.rowcount > 0

    def save_episode(self, episode: Episode) -> None:
        import time

        from ..telemetry import TelemetryManager

        t0 = time.perf_counter()
        with self._lock:
            try:
                conn = self._get_connection()
                payload_str = json.dumps({"details": episode.details, "tags": episode.tags})
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO episodes
                        (id, timestamp, event_type, summary, payload, importance)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            episode.id,
                            episode.timestamp.isoformat(),
                            "episode",
                            episode.summary,
                            payload_str,
                            episode.importance,
                        ),
                    )
                telemetry = TelemetryManager.get_instance()
                telemetry.increment("memory_writes")
                telemetry.record_latency("time_memory_ms", (time.perf_counter() - t0) * 1000)
            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Failed to save episode '{episode.id}': {exc}")

    def get_episodes(self, limit: int = 50, query: str | None = None) -> list[Episode]:
        with self._lock:
            try:
                conn = self._get_connection()
                sql = "SELECT * FROM episodes"
                params: list[Any] = []
                if query:
                    sql += " WHERE summary LIKE ?"
                    params.append(f"%{query}%")
                sql += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()
                episodes: list[Episode] = []
                for row in rows:
                    details = ""
                    tags: list[str] = []
                    if row["payload"]:
                        try:
                            payload_dict = json.loads(row["payload"])
                            details = payload_dict.get("details", "")
                            tags = payload_dict.get("tags", [])
                        except Exception:
                            pass
                    ts = (
                        datetime.fromisoformat(row["timestamp"])
                        if row["timestamp"]
                        else datetime.now(UTC)
                    )
                    episodes.append(
                        Episode(
                            id=row["id"],
                            summary=row["summary"],
                            details=details,
                            tags=tags,
                            importance=row["importance"],
                            timestamp=ts,
                        )
                    )

            except Exception as exc:
                logger = get_logger("SQLiteMemoryStore")
                logger.error(f"Failed to retrieve episodes: {exc}")
                return []
            else:
                return episodes

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
