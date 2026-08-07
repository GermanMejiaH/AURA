from __future__ import annotations

from aura.core import AURA, AURABootOptions, SystemState
from aura.events import VisualSceneProcessed
from aura.vision import VisionModule
from aura.world import CognitiveWorldModel, EntityType


def test_vision_module_integration_and_cwm_sync(tmp_path):
    options = AURABootOptions(
        enable_scheduler=False,
        enable_health_monitor=False,
        enable_cwm=True,
        enable_cognition=True,
        enable_audio=True,
        enable_vision=True,
    )
    aura = AURA(options=options)
    aura.config.set("cwm.storage_path", str(tmp_path / "cwm.json"))
    aura.boot()

    assert aura.state == SystemState.RUNNING

    vision_mod = aura.module_manager.get("vision")
    assert vision_mod is not None
    assert isinstance(vision_mod, VisionModule)

    scene_events: list[VisualSceneProcessed] = []
    aura.subscribe("VisualSceneProcessed", lambda e: scene_events.append(e))

    # Process visual scene
    result = vision_mod.process_visual_scene()
    assert len(result.persons) >= 1
    assert len(result.objects) >= 1
    assert len(result.faces) >= 1
    assert len(scene_events) == 1

    # Verify CWM updated with detected entities
    cwm = aura.container.resolve(CognitiveWorldModel)
    person_entities = [e for e in cwm.all_entities() if e.type == EntityType.PERSON]
    object_entities = [e for e in cwm.all_entities() if e.type == EntityType.OBJECT]

    assert len(person_entities) >= 1
    assert len(object_entities) >= 1

    aura.shutdown(wait=True)
    assert aura.state == SystemState.STOPPED
