from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

from .models import Entity, Relation


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CognitiveWorldModel:
    """In-memory representation of the known world as a graph of entities and relations."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entities: dict[str, Entity] = {}
        self._relations: dict[str, Relation] = {}
        self._outgoing_relations: dict[str, set[str]] = {}
        self._incoming_relations: dict[str, set[str]] = {}

    def add_entity(self, entity: Entity) -> Entity:
        with self._lock:
            self._entities[entity.id] = entity
            if entity.id not in self._outgoing_relations:
                self._outgoing_relations[entity.id] = set()
            if entity.id not in self._incoming_relations:
                self._incoming_relations[entity.id] = set()
            return entity

    def update_entity(
        self,
        entity_id: str,
        attributes: dict[str, Any] | None = None,
        name: str | None = None,
        confidence: float | None = None,
    ) -> Entity | None:
        with self._lock:
            entity = self._entities.get(entity_id)
            if entity is None:
                return None

            if name is not None:
                entity.name = name
            if attributes is not None:
                entity.attributes.update(attributes)
            if confidence is not None:
                entity.confidence = confidence
            entity.updated_at = _utcnow()
            return entity

    def remove_entity(self, entity_id: str) -> bool:
        with self._lock:
            if entity_id not in self._entities:
                return False

            del self._entities[entity_id]

            # Remove associated relations
            relations_to_remove = set()
            for rel_id, rel in self._relations.items():
                if rel.source_id == entity_id or rel.target_id == entity_id:
                    relations_to_remove.add(rel_id)

            for rel_id in relations_to_remove:
                self.remove_relation(rel_id)

            self._outgoing_relations.pop(entity_id, None)
            self._incoming_relations.pop(entity_id, None)
            return True

    def get_entity(self, entity_id: str) -> Entity | None:
        with self._lock:
            return self._entities.get(entity_id)

    def get_entity_by_name(self, name: str) -> Entity | None:
        with self._lock:
            for entity in self._entities.values():
                if entity.name.lower() == name.lower():
                    return entity
            return None

    def add_relation(self, relation: Relation) -> Relation:
        with self._lock:
            self._relations[relation.id] = relation

            if relation.source_id not in self._outgoing_relations:
                self._outgoing_relations[relation.source_id] = set()
            self._outgoing_relations[relation.source_id].add(relation.id)

            if relation.target_id not in self._incoming_relations:
                self._incoming_relations[relation.target_id] = set()
            self._incoming_relations[relation.target_id].add(relation.id)

            return relation

    def remove_relation(self, relation_id: str) -> bool:
        with self._lock:
            relation = self._relations.get(relation_id)
            if relation is None:
                return False

            del self._relations[relation_id]

            if relation.source_id in self._outgoing_relations:
                self._outgoing_relations[relation.source_id].discard(relation_id)
            if relation.target_id in self._incoming_relations:
                self._incoming_relations[relation.target_id].discard(relation_id)

            return True

    def get_relation(self, relation_id: str) -> Relation | None:
        with self._lock:
            return self._relations.get(relation_id)

    def get_relations_for_entity(self, entity_id: str, direction: str = "all") -> list[Relation]:
        with self._lock:
            rel_ids: set[str] = set()
            if direction in ("out", "outgoing", "all"):
                rel_ids.update(self._outgoing_relations.get(entity_id, set()))
            if direction in ("in", "incoming", "all"):
                rel_ids.update(self._incoming_relations.get(entity_id, set()))
            return [self._relations[rid] for rid in rel_ids if rid in self._relations]

    def all_entities(self) -> list[Entity]:
        with self._lock:
            return list(self._entities.values())

    def all_relations(self) -> list[Relation]:
        with self._lock:
            return list(self._relations.values())

    def clear(self) -> None:
        with self._lock:
            self._entities.clear()
            self._relations.clear()
            self._outgoing_relations.clear()
            self._incoming_relations.clear()

    @property
    def entities_count(self) -> int:
        with self._lock:
            return len(self._entities)

    @property
    def relations_count(self) -> int:
        with self._lock:
            return len(self._relations)
