from __future__ import annotations

import os
from typing import Any

from aura.memory import MemoryModule
from aura.memory.models import Fact, Preference
from aura.memory.store import SQLiteMemoryStore


def test_crash_recovery() -> dict[str, Any]:
    print("=== STAGE 26.4 AUDIT 2: CRASH RECOVERY & STATE HYDRATION ===")
    db_path = "scratch/test_crash.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    # 1. Setup initial store & populate state
    store1 = SQLiteMemoryStore(db_path=db_path)
    mem1 = MemoryModule(store=store1)
    mem1.semantic.add_fact(Fact(subject="usuario", predicate="nombre", object_val="Andrés"))
    mem1.semantic.add_fact(Fact(subject="usuario", predicate="edad", object_val="26"))
    mem1.preferences.set_preference("idioma", "español")

    from aura.memory.conversational import ConversationalMemory
    conv_mem1 = ConversationalMemory(store=store1)
    conv_mem1.add_turn("sess_test", "user", "Hola AURA")
    conv_mem1.add_turn("sess_test", "assistant", "¡Hola Andrés!")

    # 2. Simulate process restart (closing store1 first for clean file handle release on Windows)
    store1.close()
    del mem1
    del store1

    # 3. Instantiate new store & memory module from persisted SQLite DB
    store2 = SQLiteMemoryStore(db_path=db_path)
    mem2 = MemoryModule(store=store2)

    # 4. Verify hydration
    facts = mem2.semantic.all_facts()
    pref = mem2.preferences.get_preference("idioma")

    from aura.cognition.working_memory import WorkingMemory
    wm2 = WorkingMemory()
    hydrated_count = wm2.hydrate_from_db(store=store2, limit=10)
    turns = wm2.get_recent_conversation()

    store2.close()
    if os.path.exists(db_path):
        os.remove(db_path)

    fact_preds = {f.predicate: f.object_val for f in facts}
    has_nombre = fact_preds.get("nombre") == "Andrés"
    has_edad = fact_preds.get("edad") == "26"
    pref_val = pref.value if hasattr(pref, "value") else str(pref) if pref else None
    has_pref = pref_val == "español"
    has_turns = len(turns) >= 2

    passed = (has_nombre and has_edad and has_pref and has_turns)
    print(f"Recovered Facts: {len(facts)} | Pref: {pref} | Turns: {len(turns)} | Passed: {passed}")

    return {
        "recovered_facts": len(facts),
        "recovered_preference": pref_val,
        "recovered_turns": len(turns),
        "passed": passed,
    }


if __name__ == "__main__":
    test_crash_recovery()
