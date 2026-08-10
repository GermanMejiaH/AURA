from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from .models import Episode

if TYPE_CHECKING:
    from ..events import EventBus
    from .store import MemoryStore


class EpisodicMemory:
    """Manages episodic long-term memory (experiences, temporal logs, decisions)."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        store: MemoryStore | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.store = store
        self._episodes: list[Episode] = []
        self._lock = threading.RLock()
        if self.store is not None:
            self.load_from_store()

    def load_from_store(self) -> None:
        with self._lock:
            if self.store is not None:
                persisted = self.store.get_episodes(limit=100)
                existing_ids = {e.id for e in self._episodes}
                for ep in persisted:
                    if ep.id not in existing_ids:
                        self._episodes.append(ep)

    def record_episode(self, episode: Episode) -> Episode:
        with self._lock:
            self._episodes.append(episode)
            if self.store is not None:
                self.store.save_episode(episode)

            if self.event_bus is not None:
                from ..events import EpisodeRecorded

                self.event_bus.publish(
                    EpisodeRecorded(
                        source="EpisodicMemory",
                        episode_id=episode.id,
                        summary=episode.summary,
                    )
                )
            return episode

    def search_episodes(self, query: str, limit: int = 5) -> list[Episode]:
        with self._lock:
            if self.store is not None:
                store_results = self.store.get_episodes(query=query, limit=limit)
                if store_results:
                    return store_results

            query_lower = query.lower()
            matching = [
                e
                for e in self._episodes
                if query_lower in e.summary.lower() or query_lower in e.details.lower()
            ]
            return matching[:limit]

    def all_episodes(self) -> list[Episode]:
        with self._lock:
            if self.store is not None:
                store_results = self.store.get_episodes(limit=500)
                if store_results:
                    return store_results
            return list(self._episodes)

    def count(self) -> int:
        with self._lock:
            return len(self.all_episodes())
