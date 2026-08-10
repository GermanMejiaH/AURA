from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from .models import Preference

if TYPE_CHECKING:
    from ..events import EventBus
    from .store import MemoryStore


from .canonicalization import canonicalize_key


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
                    canon_k = canonicalize_key(pref.key)
                    if canon_k not in self._preferences:
                        self._preferences[canon_k] = Preference(
                            key=canon_k,
                            value=pref.value,
                            category=pref.category,
                            updated_at=pref.updated_at,
                        )

    def set_preference(self, key: str, value: str, category: str = "general") -> Preference:
        with self._lock:
            canon_key = canonicalize_key(key)

            # Find and clean obsolete alias keys matching the same canonical concept
            obsolete_alias_keys = [
                existing_key
                for existing_key in list(self._preferences.keys())
                if existing_key != canon_key
                and canonicalize_key(existing_key) == canon_key
            ]

            for alias_k in obsolete_alias_keys:
                self._preferences.pop(alias_k, None)
                if self.store is not None:
                    self.store.delete_preference(alias_k)

            pref = Preference(key=canon_key, value=value, category=category)
            self._preferences[canon_key] = pref
            if self.store is not None:
                self.store.save_preference(pref)

            if self.event_bus is not None:
                from ..events import PreferenceUpdated

                self.event_bus.publish(
                    PreferenceUpdated(
                        source="UserPreferencesMemory",
                        key=canon_key,
                        value=value,
                    )
                )
            return pref

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            canon_key = canonicalize_key(key)
            if self.store is not None:
                stored_pref = self.store.get_preference(canon_key)
                if stored_pref is not None:
                    self._preferences[canon_key] = stored_pref
                    return stored_pref.value

            pref = self._preferences.get(canon_key)
            return pref.value if pref is not None else default

    def all_preferences(self) -> list[Preference]:
        with self._lock:
            if self.store is not None:
                stored_prefs = self.store.get_all_preferences()
                if stored_prefs:
                    for p in stored_prefs:
                        c_key = canonicalize_key(p.key)
                        if c_key not in self._preferences:
                            self._preferences[c_key] = Preference(
                                key=c_key,
                                value=p.value,
                                category=p.category,
                                updated_at=p.updated_at,
                            )
            return list(self._preferences.values())
