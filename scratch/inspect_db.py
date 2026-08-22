import sqlite3
import os

db_path = "data/aura.db"
if not os.path.exists(db_path):
    print(f"Database file '{db_path}' does not exist!")
else:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    print("=== TABLES AND ROW COUNTS ===")
    for t in tables:
        cursor.execute(f"SELECT count(*) FROM {t}")
        cnt = cursor.fetchone()[0]
        print(f"Table: {t:35s} | Records: {cnt}")

    print("\n=== INDEXES ===")
    cursor.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index';")
    for idx in cursor.fetchall():
        print(f"Index: {idx['name']} on table '{idx['tbl_name']}' -> {idx['sql']}")

    cursor.execute("PRAGMA user_version;")
    v = cursor.fetchone()[0]
    print(f"\nSchema Version (PRAGMA user_version): V{v}")

    print("\n=== SAMPLE FACTS ===")
    cursor.execute("SELECT * FROM facts LIMIT 10;")
    facts = cursor.fetchall()
    for row in facts:
        print(dict(row))
    if not facts:
        print("(No records in facts)")

    print("\n=== SAMPLE PREFERENCES ===")
    cursor.execute("SELECT * FROM preferences LIMIT 10;")
    prefs = cursor.fetchall()
    for row in prefs:
        print(dict(row))
    if not prefs:
        print("(No records in preferences)")

    print("\n=== SAMPLE EPISODES ===")
    cursor.execute("SELECT * FROM episodes LIMIT 10;")
    episodes = cursor.fetchall()
    for row in episodes:
        print(dict(row))
    if not episodes:
        print("(No records in episodes)")

    print("\n=== AGENT PLANS & TASKS ===")
    cursor.execute("SELECT count(*) FROM agent_plans;")
    print(f"agent_plans count: {cursor.fetchone()[0]}")
    cursor.execute("SELECT count(*) FROM agent_tasks;")
    print(f"agent_tasks count: {cursor.fetchone()[0]}")

    print("\n=== MEMORY SESSIONS & TURNS ===")
    cursor.execute("SELECT count(*) FROM memory_sessions;")
    print(f"memory_sessions count: {cursor.fetchone()[0]}")
    cursor.execute("SELECT count(*) FROM conversation_turns;")
    print(f"conversation_turns count: {cursor.fetchone()[0]}")

    print("\n=== PROACTIVE TASKS & NOTIFICATIONS ===")
    cursor.execute("SELECT count(*) FROM proactive_tasks;")
    print(f"proactive_tasks count: {cursor.fetchone()[0]}")
    cursor.execute("SELECT count(*) FROM proactive_task_executions;")
    print(f"proactive_task_executions count: {cursor.fetchone()[0]}")
    cursor.execute("SELECT count(*) FROM proactive_notifications;")
    print(f"proactive_notifications count: {cursor.fetchone()[0]}")

    print("\n=== INTEGRITY CHECK & FOREIGN KEYS ===")
    cursor.execute("PRAGMA foreign_key_check;")
    fk_errors = cursor.fetchall()
    print(f"Foreign Key Violations: {len(fk_errors)}")
    for err in fk_errors:
        print(dict(err))

    cursor.execute("PRAGMA integrity_check;")
    integrity = cursor.fetchall()
    print(f"Integrity Check: {[dict(r) for r in integrity]}")

    # Check for duplicate facts or preferences
    cursor.execute("SELECT subject, predicate, object, count(*) FROM facts GROUP BY subject, predicate, object HAVING count(*) > 1;")
    dup_facts = cursor.fetchall()
    print(f"Duplicate Facts: {len(dup_facts)}")

    cursor.execute("SELECT key, count(*) FROM preferences GROUP BY key HAVING count(*) > 1;")
    dup_prefs = cursor.fetchall()
    print(f"Duplicate Preferences: {len(dup_prefs)}")

    # Check facts with invalid confidence (< 0 or > 1)
    cursor.execute("SELECT * FROM facts WHERE confidence < 0 OR confidence > 1;")
    invalid_conf = cursor.fetchall()
    print(f"Facts with Invalid Confidence: {len(invalid_conf)}")

    conn.close()
