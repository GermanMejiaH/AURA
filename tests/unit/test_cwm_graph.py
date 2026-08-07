from __future__ import annotations

from aura.world import CognitiveWorldModel, Entity, EntityType, Relation, RelationType


def test_entity_creation_and_graph_add():
    cwm = CognitiveWorldModel()
    person = Entity(name="Andrés", type=EntityType.PERSON, attributes={"role": "developer"})
    cwm.add_entity(person)

    assert cwm.entities_count == 1
    assert cwm.get_entity(person.id) is person
    assert cwm.get_entity_by_name("Andrés") is person


def test_relation_creation_and_graph_lookup():
    cwm = CognitiveWorldModel()
    person = Entity(name="Andrés", type=EntityType.PERSON)
    laptop = Entity(name="Laptop", type=EntityType.OBJECT)

    cwm.add_entity(person)
    cwm.add_entity(laptop)

    rel = Relation(
        source_id=person.id,
        target_id=laptop.id,
        relation_type=RelationType.OWNS,
    )
    cwm.add_relation(rel)

    assert cwm.relations_count == 1
    relations = cwm.get_relations_for_entity(person.id, direction="outgoing")
    assert len(relations) == 1
    assert relations[0].target_id == laptop.id


def test_remove_entity_cascades_relations():
    cwm = CognitiveWorldModel()
    person = Entity(name="Andrés", type=EntityType.PERSON)
    laptop = Entity(name="Laptop", type=EntityType.OBJECT)
    cwm.add_entity(person)
    cwm.add_entity(laptop)

    rel = Relation(
        source_id=person.id,
        target_id=laptop.id,
        relation_type=RelationType.OWNS,
    )
    cwm.add_relation(rel)

    assert cwm.entities_count == 2
    assert cwm.relations_count == 1

    cwm.remove_entity(laptop.id)
    assert cwm.entities_count == 1
    assert cwm.relations_count == 0


def test_update_entity_attributes():
    cwm = CognitiveWorldModel()
    entity = Entity(name="Robot", type=EntityType.DEVICE, attributes={"battery": 100})
    cwm.add_entity(entity)

    updated = cwm.update_entity(entity.id, attributes={"battery": 85, "status": "active"})
    assert updated is not None
    assert updated.attributes["battery"] == 85
    assert updated.attributes["status"] == "active"
