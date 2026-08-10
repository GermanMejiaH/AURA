from __future__ import annotations

from aura.autonomy import Observation
from aura.tools.base import ToolResult


def test_1_observation_creation_success() -> None:
    obs = Observation(task_id="task_001", success=True, output="Resultado ok")
    assert obs.task_id == "task_001"
    assert obs.success is True
    assert obs.output == "Resultado ok"
    assert obs.error is None


def test_2_observation_creation_failure() -> None:
    obs = Observation(task_id="task_002", success=False, error="Error de red")
    assert obs.task_id == "task_002"
    assert obs.success is False
    assert obs.output is None
    assert obs.error == "Error de red"


def test_3_from_tool_result_conversion_success() -> None:
    tr = ToolResult(success=True, output={"data": 42}, execution_time_ms=12.5)
    obs = Observation.from_tool_result(task_id="task_003", tool_result=tr)

    assert obs.task_id == "task_003"
    assert obs.success is True
    assert obs.output == {"data": 42}
    assert obs.error is None
    assert obs.metadata.get("execution_time_ms") == 12.5


def test_4_from_tool_result_conversion_failure() -> None:
    tr = ToolResult(success=False, error="División por cero", execution_time_ms=1.2)
    obs = Observation.from_tool_result(task_id="task_004", tool_result=tr)

    assert obs.task_id == "task_004"
    assert obs.success is False
    assert obs.output is None
    assert obs.error == "División por cero"
    assert obs.metadata.get("execution_time_ms") == 1.2
