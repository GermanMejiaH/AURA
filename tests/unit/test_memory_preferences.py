from __future__ import annotations

from aura.events import EventBus, PreferenceUpdated
from aura.memory import UserPreferencesMemory


def test_user_preferences_memory():
    bus = EventBus()
    prefs = UserPreferencesMemory(event_bus=bus)

    events: list[PreferenceUpdated] = []
    bus.subscribe("PreferenceUpdated", lambda e: events.append(e))

    prefs.set_preference("theme", "dark", category="ui")
    assert prefs.get_preference("theme") == "dark"
    assert prefs.get_preference("non_existent", "default_val") == "default_val"

    assert len(events) == 1
    assert events[0].key == "theme"
    assert events[0].value == "dark"
