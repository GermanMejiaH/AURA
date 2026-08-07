from __future__ import annotations

from aura.core import AURA, AURABootOptions, SystemState
from aura.events import ActionDispatched, ToolExecuted
from aura.tools import ToolsModule


def test_tools_module_integration(tmp_path):
    options = AURABootOptions(
        enable_scheduler=False,
        enable_health_monitor=False,
        enable_cwm=True,
        enable_cognition=True,
        enable_audio=True,
        enable_vision=True,
        enable_memory=True,
        enable_tools=True,
    )
    aura = AURA(options=options)
    aura.config.set("cwm.storage_path", str(tmp_path / "cwm.json"))
    aura.boot()

    assert aura.state == SystemState.RUNNING

    tools_mod = aura.module_manager.get("tools")
    assert tools_mod is not None
    assert isinstance(tools_mod, ToolsModule)

    executed_events: list[ToolExecuted] = []
    aura.subscribe("ToolExecuted", lambda e: executed_events.append(e))

    # Publish ActionDispatched matching browser tool
    aura.publish(ActionDispatched(action_type="browser", target="https://aura.ai"))

    assert len(executed_events) == 1
    assert executed_events[0].tool_name == "browser_tool"
    assert executed_events[0].success is True

    aura.shutdown(wait=True)
    assert aura.state == SystemState.STOPPED
