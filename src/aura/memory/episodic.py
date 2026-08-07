from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from .models import Episode

if TYPE_CHECKING:
    from ..events import EventBus


class EpisodicMemory:
    """Manages episodic long-term memory (experiences, temporal logs, decisions)."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self._episodes: list[Episode] = []
        self._lock = threading.RLock()

    def record_episode(self, episode: Episode) -> Episode:
        with self._lock:
            self._episodes.append(episode)

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
            query_lower = query.lower()
            matching = [
                e
                for e in self._episodes
                if query_lower in e.summary.lower() or query_lower in e.details.lower()
            ]
            return matching[:limit]

    def all_episodes(self) -> list[Episode]:
        with self._lock:
            return list(self._episodes)

    def count(self) -> int:
        with self._lock:
            return len(self._episodes)
