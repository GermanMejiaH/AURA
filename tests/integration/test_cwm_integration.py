from __future__ import annotations

from aura.core import AURA, AURABootOptions, SystemState
from aura.events import EntityCreated, RelationCreated, WorldModelUpdated
from aura.world import (
    CognitiveWorldModel,
    CWMModule,
    EntityType,
    RelationType,
    WorldQueryEngine,
)


def test_aura_boot_with_cwm_module(tmp_path):
    storage_file = tmp_path / "cwm_store.json"
    options = AURABootOptions(
        enable_scheduler=False,
        enable_health_monitor=False,
        enable_cwm=True,
    )

    aura = AURA(options=options)
    # Set CWM storage path in config
    aura.config.set("cwm.storage_path", str(storage_file))

    aura.boot()

    assert aura.state == SystemState.RUNNING
    cwm_mod = aura.module_manager.get("cwm")
    assert cwm_mod is not None
    assert isinstance(cwm_mod, CWMModule)

    # Verify IoC container has CognitiveWorldModel and WorldQueryEngine
    cwm = aura.container.resolve(CognitiveWorldModel)
    query_engine = aura.container.resolve(WorldQueryEngine)
    assert cwm is cwm_mod.cwm
    assert query_engine is cwm_mod.query_engine

    # Test incremental update via EventBus
    events_captured: list[WorldModelUpdated] = []
    aura.subscribe("WorldModelUpdated", lambda e: events_captured.append(e))

    # Publish EntityCreated
    aura.publish(
        EntityCreated(
            source="perception",
            payload={
                "entity_id": "ent_user_1",
                "name": "Andrés",
                "entity_type": EntityType.PERSON.value,
            },
        )
    )

    aura.publish(
        EntityCreated(
            source="perception",
            payload={
                "entity_id": "ent_room_1",
                "name": "Oficina",
                "entity_type": EntityType.LOCATION.value,
            },
        )
    )

    aura.publish(
        RelationCreated(
            source="perception",
            payload={
                "source_id": "ent_user_1",
                "target_id": "ent_room_1",
                "relation_type": RelationType.LOCATED_IN.value,
            },
        )
    )

    assert cwm.entities_count == 2
    assert cwm.relations_count == 1
    assert len(events_captured) == 3

    # Query via query engine
    located = query_engine.locate_object("Andrés")
    assert located is not None
    assert located.name == "Oficina"

    # Shutdown should trigger automatic persistence saving
    aura.shutdown(wait=True)
    assert aura.state == SystemState.STOPPED
    assert storage_file.exists()

    # Re-boot new AURA instance to verify automatic state restoration
    aura2 = AURA(options=options)
    aura2.config.set("cwm.storage_path", str(storage_file))
    aura2.boot()

    cwm2 = aura2.container.resolve(CognitiveWorldModel)
    assert cwm2.entities_count == 2
    assert cwm2.relations_count == 1

    aura2.shutdown(wait=True)
