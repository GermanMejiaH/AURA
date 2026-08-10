from __future__ import annotations

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import Event, EventBus
from ..logging import get_logger
from ..modules.base import BaseModule
from .consolidation import MemoryConsolidator
from .episodic import EpisodicMemory
from .models import Episode
from .preferences import UserPreferencesMemory
from .retrieval import MemoryRetrievalEngine
from .semantic import SemanticMemory
from .store import MemoryStore, SQLiteMemoryStore


class MemoryModule(BaseModule):
    """Core module managing long-term memory: Episodic, Semantic, Preferences, Retrieval."""

    name = "memory"
    description = "Long-Term Memory System - Episodic, Semantic, Preferences & Consolidation"
    priority = 25

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        container: DependencyContainer | None = None,
        event_bus: EventBus | None = None,
        store: MemoryStore | None = None,
    ) -> None:
        super().__init__(config, container, event_bus)
        db_path = (
            config.get_typed("memory.db_path", str, "data/aura.db")
            if config
            else "data/aura.db"
        )
        enabled = (
            config.get_typed("memory.enabled", bool, True)
            if config
            else True
        )

        self.store: MemoryStore | None = store
        if self.store is None and enabled:
            try:
                self.store = SQLiteMemoryStore(db_path=db_path)
            except Exception as exc:
                logger = get_logger("MemoryModule")
                logger.warning(f"Could not initialize SQLiteMemoryStore: {exc}")
                self.store = None

        self.episodic = EpisodicMemory(event_bus=event_bus, store=self.store)
        self.semantic = SemanticMemory(event_bus=event_bus, store=self.store)
        self.preferences = UserPreferencesMemory(event_bus=event_bus, store=self.store)
        self.retrieval = MemoryRetrievalEngine(
            episodic=self.episodic,
            semantic=self.semantic,
            preferences=self.preferences,
            event_bus=event_bus,
        )
        self.consolidator = MemoryConsolidator(
            episodic=self.episodic,
            semantic=self.semantic,
            event_bus=event_bus,
        )

    def on_initialize(self) -> None:
        logger = get_logger("MemoryModule")

        # Register IoC instances
        if self._container is not None:
            if self.store is not None:
                self._container.register(MemoryStore, instance=self.store)
            self._container.register(EpisodicMemory, instance=self.episodic)
            self._container.register(SemanticMemory, instance=self.semantic)
            self._container.register(UserPreferencesMemory, instance=self.preferences)
            self._container.register(MemoryRetrievalEngine, instance=self.retrieval)
            self._container.register(MemoryConsolidator, instance=self.consolidator)

        # Event Subscriptions
        self.subscribe("SpeechRecognized", self._on_speech_recognized)
        self.subscribe("GoalAchieved", self._on_goal_achieved)

        logger.info("MemoryModule initialized")

    def _on_speech_recognized(self, event: Event) -> None:
        text = getattr(event, "text", "") or event.payload.get("text", "")
        if text:
            self.episodic.record_episode(Episode(summary=f"Usuario dijo: '{text}'"))

    def _on_goal_achieved(self, event: Event) -> None:
        goal = getattr(event, "goal_id", "") or event.payload.get("goal_id", "desconocido")
        self.episodic.record_episode(
            Episode(summary=f"Objetivo cumplido: '{goal}'", importance=2.0)
        )
