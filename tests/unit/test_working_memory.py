from __future__ import annotations

import time

from aura.cognition import WorkingMemory


def test_working_memory_set_get_and_expiration():
    wm = WorkingMemory(default_ttl_seconds=0.2)
    wm.set("key1", "value1")
    assert wm.get("key1") == "value1"

    time.sleep(0.3)
    assert wm.get("key1") is None


def test_working_memory_conversation_history_and_goals():
    wm = WorkingMemory()
    wm.add_conversation_turn("user", "Hola AURA")
    wm.add_conversation_turn("assistant", "Hola, ¿en qué puedo ayudarte?")
    wm.set_active_goal("organize_day")

    history = wm.get_recent_conversation(limit=2)
    assert len(history) == 2
    assert history[0]["content"] == "Hola AURA"
    assert wm.active_goal == "organize_day"
