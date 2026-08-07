from __future__ import annotations

from aura.cognition import (
    CognitionModule,
    CognitiveState,
    CognitiveStateMachine,
    WorkingMemory,
)
from aura.core import AURA, AURABootOptions, SystemState
from aura.events import ActionDispatched, CognitiveStateChanged, StepExecuted
from aura.world import CognitiveWorldModel, Entity, EntityType


def test_cognition_module_integration_cycle(tmp_path):
    options = AURABootOptions(
        enable_scheduler=False,
        enable_health_monitor=False,
        enable_cwm=True,
        enable_cognition=True,
    )
    aura = AURA(options=options)
    aura.config.set("cwm.storage_path", str(tmp_path / "cwm.json"))
    aura.boot()

    assert aura.state == SystemState.RUNNING

    # Resolve components from IoC container
    cog_module = aura.module_manager.get("cognition")
    assert cog_module is not None
    assert isinstance(cog_module, CognitionModule)

    state_machine = aura.container.resolve(CognitiveStateMachine)
    assert state_machine.state == CognitiveState.IDLE

    cwm = aura.container.resolve(CognitiveWorldModel)
    cwm.add_entity(Entity(name="Oficina", type=EntityType.LOCATION))

    # Track cognitive events
    state_events: list[CognitiveStateChanged] = []
    action_events: list[ActionDispatched] = []
    step_events: list[StepExecuted] = []

    aura.subscribe("CognitiveStateChanged", lambda e: state_events.append(e))
    aura.subscribe("ActionDispatched", lambda e: action_events.append(e))
    aura.subscribe("StepExecuted", lambda e: step_events.append(e))

    # Process cognitive cycle
    result = cog_module.process_cognitive_cycle("Hola AURA, ¿dónde está la Oficina?")

    assert result is not None
    assert state_machine.state == CognitiveState.IDLE
    assert len(action_events) >= 1
    assert len(step_events) >= 1
    assert len(state_events) >= 2

    # Check working memory recorded turn
    wm = aura.container.resolve(WorkingMemory)
    turns = wm.get_recent_conversation(limit=5)
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[1]["role"] == "assistant"

    aura.shutdown(wait=True)
    assert aura.state == SystemState.STOPPED
