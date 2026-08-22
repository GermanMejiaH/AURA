from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from aura.memory import Episode, Fact, Preference, SQLiteMemoryStore


def test_sqlite_memory_store_fact_crud(tmp_path: Path) -> None:
    db_file = str(tmp_path / "test_facts.db")
    store = SQLiteMemoryStore(db_path=db_file)

    fact = Fact(
        subject="usuario",
        predicate="color_favorito",
        object_val="azul",
        confidence=1.0,
        source="user",
        created_at=datetime.now(UTC),
    )
    store.save_fact(fact)

    facts = store.get_facts(subject="usuario")
    assert len(facts) == 1
    assert facts[0].object_val == "azul"
    assert facts[0].predicate == "color_favorito"

    deleted = store.delete_fact(fact.id)
    assert deleted is True
    assert len(store.get_facts()) == 0
    store.close()


def test_sqlite_memory_store_preference_crud(tmp_path: Path) -> None:
    db_file = str(tmp_path / "test_prefs.db")
    store = SQLiteMemoryStore(db_path=db_file)

    pref = Preference(key="tema", value="oscuro", category="ui")
    store.save_preference(pref)

    retrieved = store.get_preference("tema")
    assert retrieved is not None
    assert retrieved.value == "oscuro"
    assert len(store.get_all_preferences()) == 1
    store.close()


def test_sqlite_memory_store_episode_crud(tmp_path: Path) -> None:
    db_file = str(tmp_path / "test_episodes.db")
    store = SQLiteMemoryStore(db_path=db_file)

    episode = Episode(summary="Conversación sobre AURA", details="Detalles del turno")
    store.save_episode(episode)

    episodes = store.get_episodes(query="AURA")
    assert len(episodes) == 1
    assert episodes[0].summary == "Conversación sobre AURA"
    store.close()


def test_sqlite_persistence_across_reopen(tmp_path: Path) -> None:
    db_file = str(tmp_path / "persisted.db")

    # Session 1: Store data & close
    store1 = SQLiteMemoryStore(db_path=db_file)
    store1.save_fact(Fact(subject="usuario", predicate="carrera", object_val="Ingeniería"))
    store1.save_preference(Preference(key="lenguaje", value="Spanish"))
    store1.close()

    assert os.path.exists(db_file)

    # Session 2: Reopen & verify
    store2 = SQLiteMemoryStore(db_path=db_file)
    facts = store2.get_facts(subject="usuario")
    pref = store2.get_preference("lenguaje")

    assert len(facts) == 1
    assert facts[0].object_val == "Ingeniería"
    assert pref is not None
    assert pref.value == "Spanish"
    store2.close()


def test_sqlite_migration_from_legacy_v0_schema(tmp_path: Path) -> None:
    """Stage 24: Test migration from legacy V0 schema (object_val & details/tags)."""
    db_file = str(tmp_path / "legacy_v0.db")

    # 1. Create legacy V0 database manually
    conn = sqlite3.connect(db_file)
    with conn:
        conn.execute("PRAGMA user_version = 0;")
        conn.execute(
            """
            CREATE TABLE facts (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_val TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE episodes (
                id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                importance REAL NOT NULL DEFAULT 1.0
            );
            """
        )
        # Insert sample legacy records
        conn.execute(
            "INSERT INTO facts VALUES ('f1', 'user', 'fav_color', 'blue', 1.0, 'user', ?);",
            (datetime.now(UTC).isoformat(),),
        )
        conn.execute(
            "INSERT INTO episodes VALUES "
            "('e1', 'Chat episode', 'User asked about time', ?, '[\"chat\"]', 1.0);",
            (datetime.now(UTC).isoformat(),),
        )
    conn.close()

    # 2. Instantiate SQLiteMemoryStore to run V0 -> V1 migration
    store = SQLiteMemoryStore(db_path=db_file)

    # 3. Verify user_version updated to 1
    conn_verify = sqlite3.connect(db_file)
    cur = conn_verify.cursor()
    cur.execute("PRAGMA user_version;")
    assert cur.fetchone()[0] == 1
    conn_verify.close()

    # 4. Verify data retrieval via store API
    facts = store.get_facts(subject="user")
    assert len(facts) == 1
    assert facts[0].object_val == "blue"

    episodes = store.get_episodes(query="Chat")
    assert len(episodes) == 1
    assert episodes[0].summary == "Chat episode"
    assert episodes[0].details == "User asked about time"
    assert episodes[0].tags == ["chat"]

    # 5. Verify save_fact and save_episode work after migration
    store.save_fact(Fact(subject="user", predicate="city", object_val="Madrid"))
    store.save_episode(Episode(summary="New episode post migration", details="Clean details"))

    assert len(store.get_facts(subject="user")) == 2
    assert len(store.get_episodes()) == 2
    store.close()


def test_migration_preserves_existing_data(tmp_path: Path) -> None:
    """Stage 24: Verify 100% data preservation during migration."""
    db_file = str(tmp_path / "preserve_data.db")

    conn = sqlite3.connect(db_file)
    with conn:
        conn.execute("PRAGMA user_version = 0;")
        conn.execute(
            """
            CREATE TABLE facts (
                id TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL,
                object_val TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE episodes (
                id TEXT PRIMARY KEY, summary TEXT NOT NULL, details TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
                importance REAL NOT NULL DEFAULT 1.0
            );
            """
        )
        for i in range(10):
            conn.execute(
                "INSERT INTO facts VALUES "
                f"('f_{i}', 'sub_{i}', 'pred_{i}', 'obj_{i}', 1.0, 'user', ?);",
                (datetime.now(UTC).isoformat(),),
            )
        for i in range(50):
            conn.execute(
                "INSERT INTO episodes VALUES "
                f"('e_{i}', 'summary_{i}', 'details_{i}', ?, '[\"tag_{i}\"]', 1.0);",
                (datetime.now(UTC).isoformat(),),
            )
    conn.close()

    store = SQLiteMemoryStore(db_path=db_file)
    assert len(store.get_facts()) == 10
    assert len(store.get_episodes(limit=100)) == 50
    store.close()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    """Stage 24: Verify migration running multiple times does not alter data or re-run."""
    db_file = str(tmp_path / "idempotent.db")

    # Run 1
    store1 = SQLiteMemoryStore(db_path=db_file)
    store1.save_fact(Fact(subject="u", predicate="p", object_val="o"))
    store1.close()

    # Run 2 (Should skip migration since user_version is already 1)
    store2 = SQLiteMemoryStore(db_path=db_file)
    facts = store2.get_facts(subject="u")
    assert len(facts) == 1
    assert facts[0].object_val == "o"
    store2.close()


def test_migration_rollback_on_failure(tmp_path: Path) -> None:
    """Stage 24: Verify atomic rollback if migration encounters an error."""
    db_file = str(tmp_path / "rollback_fail.db")

    conn = sqlite3.connect(db_file)
    with conn:
        conn.execute("PRAGMA user_version = 0;")
        conn.execute(
            """
            CREATE TABLE facts (
                id TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL,
                object_val TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL
            );
            """
        )
        conn.execute("INSERT INTO facts VALUES ('f1', 'user', 'key', 'val', 1.0, 'user', 'now');")
    conn.close()

    class FailingStore(SQLiteMemoryStore):
        def _migrate_v0_to_v1(self, conn: sqlite3.Connection) -> None:
            # Partial work then raise exception
            conn.execute("ALTER TABLE facts RENAME COLUMN object_val TO object;")
            raise RuntimeError("Controlled migration failure")

    try:
        FailingStore(db_path=db_file)
    except Exception:
        pass

    # Verify user_version remains 0 after failure rollback
    conn_verify = sqlite3.connect(db_file)
    cur = conn_verify.cursor()
    cur.execute("PRAGMA user_version;")
    assert cur.fetchone()[0] == 0

    # Verify table column object_val was rolled back by SQLite transaction
    cur.execute("PRAGMA table_info(facts);")
    cols = [r[1] for r in cur.fetchall()]
    assert "object_val" in cols
    assert "object" not in cols
    conn_verify.close()


def test_current_schema_integrity(tmp_path: Path) -> None:
    """Stage 24: Verify all tables have expected columns in current schema."""
    db_file = str(tmp_path / "schema_check.db")
    store = SQLiteMemoryStore(db_path=db_file)

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(facts);")
    fact_cols = [r[1] for r in cur.fetchall()]
    assert "object" in fact_cols
    assert "object_val" not in fact_cols

    cur.execute("PRAGMA table_info(episodes);")
    ep_cols = [r[1] for r in cur.fetchall()]
    assert "event_type" in ep_cols
    assert "payload" in ep_cols

    conn.close()
    store.close()


def test_real_database_schema_integrity() -> None:
    """Stage 24: Inspect data/aura.db if present to verify user_version 1 and schema integrity."""
    db_file = "data/aura.db"
    if not os.path.exists(db_file):
        return

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    cur.execute("PRAGMA user_version;")
    v = cur.fetchone()[0]
    assert v == 1, f"Expected data/aura.db user_version == 1, got {v}"

    cur.execute("PRAGMA table_info(facts);")
    fact_cols = [r[1] for r in cur.fetchall()]
    assert "object" in fact_cols, "Column 'object' missing in facts table of data/aura.db"

    cur.execute("PRAGMA table_info(episodes);")
    ep_cols = [r[1] for r in cur.fetchall()]
    assert "event_type" in ep_cols, "Column 'event_type' missing in episodes table of data/aura.db"
    assert "payload" in ep_cols, "Column 'payload' missing in episodes table of data/aura.db"

    cur.execute("PRAGMA quick_check;")
    assert cur.fetchone()[0] == "ok", "Integrity check failed for data/aura.db"

    conn.close()
