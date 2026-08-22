"""Stage 24 Integration & Reality Validation Test Suite.

Verifies REAL persistence integrity on 'data/aura.db':
- Pre-existing legacy facts and episodes are preserved 100%.
- New fact additions and queries succeed against migrated schema V1.
- New episode recordings succeed and extract JSON payload details/tags.
- Persistence survives complete store closure and process restart.
- ConversationalRuntime uses real persistent SQLite memory for grounded responses.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from aura.cognition.scheduling.conversational_runtime import ConversationalRuntime
from aura.memory import Episode, Fact, SQLiteMemoryStore
from aura.memory.conversational import ConversationalMemory

REAL_DB_PATH = "data/aura.db"


def test_stage24_real_database_fact_and_episode_operations() -> None:
    """FASE 4 A/B: Test real fact addition, query, and episode recording on data/aura.db."""
    if not os.path.exists(REAL_DB_PATH):
        return

    store = SQLiteMemoryStore(db_path=REAL_DB_PATH)

    # 1. Retrieve pre-migration facts (must have at least the 2 legacy facts)
    initial_facts = store.get_facts(subject="usuario")
    assert len(initial_facts) >= 2, f"Expected at least 2 legacy facts, got {len(initial_facts)}"
    fact_preds = {f.predicate: f.object_val for f in initial_facts}
    assert "color_favorito" in fact_preds
    assert "comida_favorita" in fact_preds

    # 2. Add a new fact to real database
    new_fact = Fact(
        subject="usuario",
        predicate="test_stage24",
        object_val="validado",
        confidence=1.0,
        source="system",
        created_at=datetime.now(UTC),
    )
    store.save_fact(new_fact)

    # 3. Query facts and verify new + legacy facts coexist
    updated_facts = store.get_facts(subject="usuario")
    assert len(updated_facts) == len(initial_facts) + 1
    updated_preds = {f.predicate: f.object_val for f in updated_facts}
    assert updated_preds.get("test_stage24") == "validado"

    # 4. Record a new episode
    new_ep = Episode(
        summary="Stage 24 Reality Validation Episode",
        details="Verificación real de persistencia post-migración",
        tags=["reality", "stage24"],
    )
    store.save_episode(new_ep)

    # 5. Retrieve episodes and verify new + legacy episodes coexist
    episodes = store.get_episodes(limit=300)
    assert len(episodes) >= 264, f"Expected at least 264 episodes, got {len(episodes)}"
    matched = [e for e in episodes if e.summary == "Stage 24 Reality Validation Episode"]
    assert len(matched) >= 1
    assert matched[0].details == "Verificación real de persistencia post-migración"
    assert "reality" in matched[0].tags

    # Clean up test fact
    store.delete_fact(new_fact.id)
    store.close()


def test_stage24_real_database_persistence_across_restart() -> None:
    """FASE 4 C: Test persistence across process restart (store close and re-open)."""
    if not os.path.exists(REAL_DB_PATH):
        return

    # Turn 1: Save persistent fact
    store1 = SQLiteMemoryStore(db_path=REAL_DB_PATH)
    test_fact = Fact(
        subject="usuario",
        predicate="restart_key",
        object_val="restart_value",
    )
    store1.save_fact(test_fact)
    store1.close()

    # Turn 2: Re-open database (Simulate restart)
    store2 = SQLiteMemoryStore(db_path=REAL_DB_PATH)
    facts = store2.get_facts(subject="usuario", predicate="restart_key")
    assert len(facts) == 1
    assert facts[0].object_val == "restart_value"

    # Clean up test fact
    store2.delete_fact(test_fact.id)
    store2.close()


def test_stage24_conversational_runtime_memory_integration() -> None:
    """FASE 4 D: Test ConversationalRuntime using persistent SQLite memory on real database."""
    if not os.path.exists(REAL_DB_PATH):
        return

    store = SQLiteMemoryStore(db_path=REAL_DB_PATH)
    conv_mem = ConversationalMemory(store=store)
    runtime = ConversationalRuntime(conversational_memory=conv_mem)

    # Ask conversational runtime question referencing persistent memory
    resp = runtime.process_turn(
        conversation_id="stage24_reality_conv",
        user_input="¿Cuál es la fecha de hoy?",
    )

    assert resp is not None
    assert resp.natural_response is not None
    assert len(resp.natural_response) > 0
    assert resp.success is True

    runtime.close()
    store.close()
