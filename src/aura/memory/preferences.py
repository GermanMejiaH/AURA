from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from .models import Preference

if TYPE_CHECKING:
    from ..events import EventBus


class UserPreferencesMemory:
    """Manages persistent user preferences, settings, and habits."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self._preferences: dict[str, Preference] = {}
        self._lock = threading.RLock()

    def set_preference(self, key: str, value: str, category: str = "general") -> Preference:
        with self._lock:
            pref = Preference(key=key, value=value, category=category)
            self._preferences[key] = pref

            if self.event_bus is not None:
                from ..events import PreferenceUpdated

                self.event_bus.publish(
                    PreferenceUpdated(
                        source="UserPreferencesMemory",
                        key=key,
                        value=value,
                    )
                )
            return pref

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            pref = self._preferences.get(key)
            return pref.value if pref is not None else default

    def all_preferences(self) -> list[Preference]:
        with self._lock:
            return list(self._preferences.values())
