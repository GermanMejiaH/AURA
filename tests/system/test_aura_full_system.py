from __future__ import annotations

from aura.autonomy import AutonomyModule
from aura.core import AURA, AURABootOptions, SystemState
from aura.events import (
    ActionDispatched,
    GoalAchieved,
    GoalSet,
    ObjectDetected,
    SpeechRecognized,
)


def test_aura_full_multimodal_system_pipeline(tmp_path):
    """System-level test verifying full multimodal integration across all 8 modules."""
    options = AURABootOptions(
        enable_scheduler=False,
        enable_health_monitor=False,
        enable_cwm=True,
        enable_cognition=True,
        enable_audio=True,
        enable_vision=True,
        enable_memory=True,
        enable_tools=True,
        enable_robotics=True,
        enable_autonomy=True,
    )
    aura = AURA(options=options)
    aura.config.set("cwm.storage_path", str(tmp_path / "full_cwm.json"))
    aura.boot()

    assert aura.state == SystemState.RUNNING
    assert len(aura.module_manager.list_modules()) == 8

    # Track events across all modules
    events_log: list[str] = []

    aura.subscribe("SpeechRecognized", lambda e: events_log.append("SpeechRecognized"))
    aura.subscribe("EpisodeRecorded", lambda e: events_log.append("EpisodeRecorded"))
    aura.subscribe("ObjectDetected", lambda e: events_log.append("ObjectDetected"))
    aura.subscribe("ToolExecuted", lambda e: events_log.append("ToolExecuted"))
    aura.subscribe(
        "NavigationTargetReached", lambda e: events_log.append("NavigationTargetReached")
    )
    aura.subscribe("ObjectManipulated", lambda e: events_log.append("ObjectManipulated"))
    aura.subscribe("PolicyUpdated", lambda e: events_log.append("PolicyUpdated"))

    # 1. User Voice Input
    aura.publish(SpeechRecognized(text="AURA, busca el reporte y navega a la mesa"))

    # 2. Vision Perception
    aura.publish(ObjectDetected(label="table", confidence=0.98))

    # 3. Tool Dispatch
    aura.publish(ActionDispatched(action_type="browser", target="https://report.aura.ai"))

    # 4. Robotics Dispatch (Navigation & Manipulation)
    aura.publish(ActionDispatched(action_type="navigate", payload={"x": 2.5, "y": 3.5}))
    aura.publish(
        ActionDispatched(
            action_type="grasp", payload={"target_object_id": "document_folder"}
        )
    )

    # 5. Autonomy Goal Dispatch
    aura.publish(GoalSet(description="Navegación y recolección autónoma completada"))

    autonomy_mod = aura.module_manager.get("autonomy")
    assert isinstance(autonomy_mod, AutonomyModule)
    goals = autonomy_mod.goals.get_active_goals()
    assert len(goals) >= 1

    aura.publish(GoalAchieved(goal_id=goals[0].goal_id))

    # Verify cross-module processing
    assert "SpeechRecognized" in events_log
    assert "EpisodeRecorded" in events_log
    assert "ObjectDetected" in events_log
    assert "ToolExecuted" in events_log
    assert "NavigationTargetReached" in events_log
    assert "ObjectManipulated" in events_log
    assert "PolicyUpdated" in events_log

    aura.shutdown(wait=True)
    assert aura.state == SystemState.STOPPED
