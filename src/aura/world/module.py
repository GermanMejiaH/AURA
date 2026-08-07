from __future__ import annotations

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import (
    Event,
    EventBus,
    WorldModelUpdated,
)
from ..logging import get_logger
from ..modules.base import BaseModule
from .graph import CognitiveWorldModel
from .models import Entity, Relation
from .persistence import CWMPersistenceProvider
from .query import WorldQueryEngine


class CWMModule(BaseModule):
    """Core module responsible for managing the Cognitive World Model state and lifecycle."""

    name = "cwm"
    description = "Cognitive World Model - Single Source of Truth for World State"
    priority = 10

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        container: DependencyContainer | None = None,
        event_bus: EventBus | None = None,
        cwm: CognitiveWorldModel | None = None,
    ) -> None:
        super().__init__(config, container, event_bus)
        self.cwm = cwm if cwm is not None else CognitiveWorldModel()
        self.query_engine = WorldQueryEngine(self.cwm)
        self.persistence: CWMPersistenceProvider | None = None

    def on_initialize(self) -> None:
        logger = get_logger("CWMModule")
        storage_path = "data/cwm_store.json"
        if self._config is not None:
            storage_path = self._config.get_typed("cwm.storage_path", str, "data/cwm_store.json")

        self.persistence = CWMPersistenceProvider(storage_path=storage_path)
        try:
            self.persistence.load(self.cwm)
            logger.info(
                f"Loaded CWM from {storage_path} ({self.cwm.entities_count} entities, "
                f"{self.cwm.relations_count} relations)"
            )
        except Exception:
            logger.exception(f"Failed to load CWM persistence from {storage_path}")

        # Register IoC instances
        if self._container is not None:
            self._container.register(CognitiveWorldModel, instance=self.cwm)
            self._container.register(WorldQueryEngine, instance=self.query_engine)

        # Event Subscriptions
        self.subscribe("EntityCreated", self._on_entity_created)
        self.subscribe("EntityUpdated", self._on_entity_updated)
        self.subscribe("EntityDeleted", self._on_entity_deleted)
        self.subscribe("RelationCreated", self._on_relation_created)
        self.subscribe("RelationDeleted", self._on_relation_deleted)

    def on_stop(self) -> None:
        logger = get_logger("CWMModule")
        if self.persistence is not None:
            try:
                saved_path = self.persistence.save(self.cwm)
                logger.info(
                    f"Saved CWM persistence to {saved_path} ({self.cwm.entities_count} entities, "
                    f"{self.cwm.relations_count} relations)"
                )
            except Exception:
                logger.exception("Failed to save CWM state during shutdown")

    def _on_entity_created(self, event: Event) -> None:
        payload = event.payload
        if "entity" in payload and isinstance(payload["entity"], Entity):
            ent = payload["entity"]
        elif "name" in payload:
            ent = Entity(
                id=str(payload.get("entity_id", payload.get("id"))),
                name=payload["name"],
                type=payload.get("entity_type", payload.get("type", "object")),
                attributes=payload.get("attributes", {}),
                confidence=float(payload.get("confidence", 1.0)),
                source=event.source,
            )
        else:
            return

        self.cwm.add_entity(ent)
        self.publish(
            WorldModelUpdated(
                source=self.name,
                entities_count=self.cwm.entities_count,
                relations_count=self.cwm.relations_count,
                change_type="entity_created",
            )
        )

    def _on_entity_updated(self, event: Event) -> None:
        payload = event.payload
        entity_id = payload.get("entity_id")
        if not entity_id:
            return

        self.cwm.update_entity(
            entity_id=str(entity_id),
            attributes=payload.get("attributes"),
            name=payload.get("name"),
            confidence=payload.get("confidence"),
        )
        self.publish(
            WorldModelUpdated(
                source=self.name,
                entities_count=self.cwm.entities_count,
                relations_count=self.cwm.relations_count,
                change_type="entity_updated",
            )
        )

    def _on_entity_deleted(self, event: Event) -> None:
        entity_id = event.payload.get("entity_id")
        if entity_id and self.cwm.remove_entity(str(entity_id)):
            self.publish(
                WorldModelUpdated(
                    source=self.name,
                    entities_count=self.cwm.entities_count,
                    relations_count=self.cwm.relations_count,
                    change_type="entity_deleted",
                )
            )

    def _on_relation_created(self, event: Event) -> None:
        payload = event.payload
        if "relation" in payload and isinstance(payload["relation"], Relation):
            rel = payload["relation"]
        elif "source_id" in payload and "target_id" in payload:
            rel = Relation(
                source_id=str(payload["source_id"]),
                target_id=str(payload["target_id"]),
                relation_type=payload.get("relation_type", "connected_to"),
                attributes=payload.get("attributes", {}),
                confidence=float(payload.get("confidence", 1.0)),
                source=event.source,
            )
        else:
            return

        self.cwm.add_relation(rel)
        self.publish(
            WorldModelUpdated(
                source=self.name,
                entities_count=self.cwm.entities_count,
                relations_count=self.cwm.relations_count,
                change_type="relation_created",
            )
        )

    def _on_relation_deleted(self, event: Event) -> None:
        rel_id = event.payload.get("relation_id")
        if rel_id and self.cwm.remove_relation(str(rel_id)):
            self.publish(
                WorldModelUpdated(
                    source=self.name,
                    entities_count=self.cwm.entities_count,
                    relations_count=self.cwm.relations_count,
                    change_type="relation_deleted",
                )
            )
