from __future__ import annotations

from aura.events import (
    ToolConfirmationRequired,
    ToolExecuted,
    ToolExecutionStarted,
    ToolFailed,
    ToolRequested,
)


def test_tool_events_instantiation_and_dict() -> None:
    req = ToolRequested(tool_name="datetime_tool", raw_text="¿Qué hora es?")
    assert req.event_name() == "ToolRequested"
    assert req.tool_name == "datetime_tool"

    started = ToolExecutionStarted(tool_name="datetime_tool")
    assert started.event_name() == "ToolExecutionStarted"

    executed = ToolExecuted(tool_name="datetime_tool", success=True, execution_time_ms=1.5)
    assert executed.event_name() == "ToolExecuted"

    failed = ToolFailed(tool_name="calculator_tool", error="Division by zero")
    assert failed.event_name() == "ToolFailed"

    conf = ToolConfirmationRequired(
        tool_name="shell_tool", risk_level="destructive", reason="High risk action"
    )
    assert conf.event_name() == "ToolConfirmationRequired"
    assert conf.risk_level == "destructive"
