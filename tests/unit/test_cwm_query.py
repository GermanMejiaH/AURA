from __future__ import annotations

from aura.world import (
    CognitiveWorldModel,
    Entity,
    EntityType,
    Relation,
    RelationType,
    WorldQueryEngine,
)


def test_query_locate_object_and_who_is_present():
    cwm = CognitiveWorldModel()
    query_engine = WorldQueryEngine(cwm)

    office = Entity(name="Oficina Principal", type=EntityType.LOCATION)
    user = Entity(name="Andrés", type=EntityType.PERSON)
    mug = Entity(name="Taza de Café", type=EntityType.OBJECT)

    cwm.add_entity(office)
    cwm.add_entity(user)
    cwm.add_entity(mug)

    # Andrés is in Office
    cwm.add_relation(
        Relation(source_id=user.id, target_id=office.id, relation_type=RelationType.LOCATED_IN)
    )
    # Mug is in Office
    cwm.add_relation(
        Relation(source_id=mug.id, target_id=office.id, relation_type=RelationType.LOCATED_IN)
    )

    # Test locate_object
    located_office = query_engine.locate_object("Taza de Café")
    assert located_office is not None
    assert located_office.id == office.id

    # Test who_is_present
    present_people = query_engine.who_is_present("Oficina Principal")
    assert len(present_people) == 1
    assert present_people[0].id == user.id


def test_query_find_entities_and_neighbors():
    cwm = CognitiveWorldModel()
    query_engine = WorldQueryEngine(cwm)

    sensor1 = Entity(name="Cámara 1", type=EntityType.DEVICE, attributes={"type": "camera"})
    sensor2 = Entity(name="Sensor Tº", type=EntityType.DEVICE, attributes={"type": "temp"})
    cwm.add_entity(sensor1)
    cwm.add_entity(sensor2)

    cameras = query_engine.find_entities(
        entity_type=EntityType.DEVICE, attributes_filter={"type": "camera"}
    )
    assert len(cameras) == 1
    assert cameras[0].name == "Cámara 1"
