from __future__ import annotations

from typing import Any

from .graph import CognitiveWorldModel
from .models import Entity, EntityType, RelationType


class WorldQueryEngine:
    """Semantic query engine over the Cognitive World Model graph."""

    def __init__(self, cwm: CognitiveWorldModel) -> None:
        self._cwm = cwm

    def find_entities(
        self,
        entity_type: EntityType | str | None = None,
        name_contains: str | None = None,
        attributes_filter: dict[str, Any] | None = None,
        min_confidence: float = 0.0,
    ) -> list[Entity]:
        results: list[Entity] = []

        type_str = entity_type.value if isinstance(entity_type, EntityType) else entity_type

        for entity in self._cwm.all_entities():
            if entity.confidence < min_confidence:
                continue

            if type_str is not None:
                ent_type = entity.type.value if isinstance(entity.type, EntityType) else entity.type
                if ent_type != type_str:
                    continue

            if name_contains is not None:
                if name_contains.lower() not in entity.name.lower():
                    continue

            if attributes_filter:
                match = True
                for key, val in attributes_filter.items():
                    if entity.attributes.get(key) != val:
                        match = False
                        break
                if not match:
                    continue

            results.append(entity)

        return results

    def locate_object(self, object_name_or_id: str) -> Entity | None:
        """Find the location entity where an object is located."""
        target_entity: Entity | None = self._cwm.get_entity(object_name_or_id)
        if target_entity is None:
            target_entity = self._cwm.get_entity_by_name(object_name_or_id)
        if target_entity is None:
            return None

        relations = self._cwm.get_relations_for_entity(target_entity.id, direction="outgoing")
        for rel in relations:
            rel_type = (
                rel.relation_type.value
                if isinstance(rel.relation_type, RelationType)
                else rel.relation_type
            )
            if rel_type == RelationType.LOCATED_IN.value:
                return self._cwm.get_entity(rel.target_id)
        return None

    def who_is_present(self, location_id_or_name: str | None = None) -> list[Entity]:
        """Find all persons present in the specified location or in the world."""
        people = self.find_entities(entity_type=EntityType.PERSON)
        if location_id_or_name is None:
            return people

        loc_entity = self._cwm.get_entity(location_id_or_name)
        if loc_entity is None:
            loc_entity = self._cwm.get_entity_by_name(location_id_or_name)
        if loc_entity is None:
            return []

        present: list[Entity] = []
        for person in people:
            loc = self.locate_object(person.id)
            if loc and loc.id == loc_entity.id:
                present.append(person)
        return present

    def get_available_capabilities(self) -> list[Entity]:
        """Get all capabilities currently available in the CWM."""
        return self.find_entities(entity_type=EntityType.CAPABILITY)

    def get_neighbors(
        self,
        entity_id: str,
        relation_type: RelationType | str | None = None,
        direction: str = "all",
    ) -> list[Entity]:
        """Find neighboring entities connected to entity_id by relation_type."""
        relations = self._cwm.get_relations_for_entity(entity_id, direction=direction)
        target_ids: set[str] = set()

        type_str = relation_type.value if isinstance(relation_type, RelationType) else relation_type

        for rel in relations:
            r_type = (
                rel.relation_type.value
                if isinstance(rel.relation_type, RelationType)
                else rel.relation_type
            )
            if type_str is not None and r_type != type_str:
                continue

            if rel.source_id == entity_id:
                target_ids.add(rel.target_id)
            if rel.target_id == entity_id:
                target_ids.add(rel.source_id)

        neighbors: list[Entity] = []
        for tid in target_ids:
            e = self._cwm.get_entity(tid)
            if e is not None:
                neighbors.append(e)

        return neighbors
