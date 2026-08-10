from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from .models import Preference

if TYPE_CHECKING:
    from ..events import EventBus
    from .store import MemoryStore


class UserPreferencesMemory:
    """Manages persistent user preferences, settings, and habits."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        store: MemoryStore | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.store = store
        self._preferences: dict[str, Preference] = {}
        self._lock = threading.RLock()
        if self.store is not None:
            self.load_from_store()

    def load_from_store(self) -> None:
        with self._lock:
            if self.store is not None:
                persisted = self.store.get_all_preferences()
                for pref in persisted:
                    if pref.key not in self._preferences:
                        self._preferences[pref.key] = pref

    def set_preference(self, key: str, value: str, category: str = "general") -> Preference:
        with self._lock:
            pref = Preference(key=key, value=value, category=category)
            self._preferences[key] = pref
            if self.store is not None:
                self.store.save_preference(pref)

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
            if self.store is not None:
                stored_pref = self.store.get_preference(key)
                if stored_pref is not None:
                    self._preferences[key] = stored_pref
                    return stored_pref.value

            pref = self._preferences.get(key)
            return pref.value if pref is not None else default

    def all_preferences(self) -> list[Preference]:
        with self._lock:
            if self.store is not None:
                stored_prefs = self.store.get_all_preferences()
                if stored_prefs:
                    for p in stored_prefs:
                        self._preferences[p.key] = p
            return list(self._preferences.values())
