from __future__ import annotations

from aura.tools import BaseTool, ToolMetadata, ToolRegistry, ToolResult


class CustomDummyTool(BaseTool):
    metadata = ToolMetadata(name="dummy", description="Dummy tool for testing", category="test")

    def execute(self, **kwargs: object) -> ToolResult:
        if kwargs.get("fail"):
            raise ValueError("Test error")
        return ToolResult(success=True, output="dummy_ok")


def test_tool_registry_registration_and_execution():
    registry = ToolRegistry()
    dummy = CustomDummyTool()

    registry.register(dummy)
    assert registry.get("dummy") is not None
    assert len(registry.list_metadata()) == 1

    res_ok = registry.execute("dummy", fail=False)
    assert res_ok.success is True
    assert res_ok.output == "dummy_ok"

    res_fail = registry.execute("dummy", fail=True)
    assert res_fail.success is False
    assert "Test error" in (res_fail.error or "")

    res_missing = registry.execute("unknown_tool")
    assert res_missing.success is False
    assert "not found" in (res_missing.error or "")
