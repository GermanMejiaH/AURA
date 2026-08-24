from __future__ import annotations

import os
import sqlite3
from typing import Any

from aura.memory.models import Fact
from aura.memory.store import SQLiteMemoryStore


def test_sqlite_durability() -> dict[str, Any]:
    print("=== STAGE 26.4 AUDIT 3: SQLITE DURABILITY & WAL MODE ===")
    db_path = "scratch/test_wal.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    store = SQLiteMemoryStore(db_path=db_path)
    conn = store._get_connection()

    # 1. WAL mode check
    cur = conn.execute("PRAGMA journal_mode;")
    j_mode = cur.fetchone()[0].lower()

    # 2. Busy timeout check
    cur = conn.execute("PRAGMA busy_timeout;")
    b_timeout = cur.fetchone()[0]

    # 3. Transaction Rollback & Commit Integrity
    fact_good = Fact(subject="usuario", predicate="ciudad", object_val="Medellín")
    store.save_fact(fact_good)

    rollback_passed = False
    try:
        with conn:
            conn.execute("INSERT INTO facts (id, subject, predicate, object, confidence, source, created_at) VALUES ('f1', 'u', 'p', 'v', 1.0, 'sys', 'now')")
            # Trigger constraint error with duplicate PRIMARY KEY 'f1'
            conn.execute("INSERT INTO facts (id, subject, predicate, object, confidence, source, created_at) VALUES ('f1', 'u', 'p', 'v', 1.0, 'sys', 'now')")
    except sqlite3.IntegrityError:
        rollback_passed = True

    # Verify rollback did not persist f1
    cur = conn.execute("SELECT COUNT(*) FROM facts WHERE id = 'f1'")
    f1_count = cur.fetchone()[0]

    store.close()
    if os.path.exists(db_path):
        os.remove(db_path)

    passed = (j_mode == "wal" and b_timeout >= 5000 and rollback_passed and f1_count == 0)
    print(f"Journal Mode: '{j_mode}' | Busy Timeout: {b_timeout}ms | Rollback Success: {rollback_passed} (Count={f1_count}) | Passed: {passed}")

    return {
        "journal_mode": j_mode,
        "busy_timeout": b_timeout,
        "rollback_success": rollback_passed,
        "uncommitted_count": f1_count,
        "passed": passed,
    }


if __name__ == "__main__":
    test_sqlite_durability()
