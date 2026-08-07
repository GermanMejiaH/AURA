from __future__ import annotations

from aura.world import (
    CognitiveWorldModel,
    CWMPersistenceProvider,
    Entity,
    EntityType,
    Relation,
    RelationType,
)


def test_cwm_json_persistence_save_and_load(tmp_path):
    storage_file = tmp_path / "cwm_test.json"
    provider = CWMPersistenceProvider(storage_path=storage_file)

    cwm = CognitiveWorldModel()
    room = Entity(name="Sala de Estar", type=EntityType.LOCATION)
    tv = Entity(name="Televisor", type=EntityType.DEVICE)
    cwm.add_entity(room)
    cwm.add_entity(tv)
    cwm.add_relation(
        Relation(source_id=tv.id, target_id=room.id, relation_type=RelationType.LOCATED_IN)
    )

    saved_path = provider.save(cwm)
    assert saved_path.exists()

    # Load into new CWM instance
    new_cwm = CognitiveWorldModel()
    provider.load(new_cwm)

    assert new_cwm.entities_count == 2
    assert new_cwm.relations_count == 1

    loaded_tv = new_cwm.get_entity(tv.id)
    assert loaded_tv is not None
    assert loaded_tv.name == "Televisor"
