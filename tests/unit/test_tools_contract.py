from __future__ import annotations

from typing import Any

from aura.tools.base import BaseTool, ToolMetadata, ToolResult
from aura.tools.registry import ToolRegistry


class DummySchemaTool(BaseTool):
    metadata = ToolMetadata(
        name="dummy_tool",
        description="Dummy tool with schema for testing",
        category="testing",
        parameters_schema={
            "required": ["action"],
            "properties": {
                "action": {"type": "string", "enum": ["read", "write"]},
                "count": {"type": "integer"},
            },
        },
        risk_level="safe",
        requires_confirmation=False,
        read_only=True,
    )

    def execute(self, action: str = "read", count: int = 1, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output=f"Executed {action} with count {count}")


def test_tool_metadata_defaults_and_fields() -> None:
    meta = ToolMetadata(name="test_tool", description="Test tool description")
    assert meta.risk_level == "safe"
    assert meta.requires_confirmation is False
    assert meta.read_only is True

    # Test invalid risk level fallback
    meta_invalid = ToolMetadata(
        name="invalid_tool",
        description="Invalid risk level",
        risk_level="unknown_risk",
    )
    assert meta_invalid.risk_level == "safe"


def test_tool_registry_validation_success() -> None:
    registry = ToolRegistry()
    tool = DummySchemaTool()
    registry.register(tool)

    valid, err = registry.validate_parameters("dummy_tool", action="read", count=5)
    assert valid is True
    assert err is None

    res = registry.execute("dummy_tool", action="read", count=5)
    assert res.success is True
    assert res.output == "Executed read with count 5"


def test_tool_registry_validation_missing_required() -> None:
    registry = ToolRegistry()
    tool = DummySchemaTool()
    registry.register(tool)

    valid, err = registry.validate_parameters("dummy_tool", count=5)
    assert valid is False
    assert err is not None
    assert "Missing required parameter 'action'" in err

    res = registry.execute("dummy_tool", count=5)
    assert res.success is False
    assert "Missing required parameter 'action'" in res.error  # type: ignore[operator]


def test_tool_registry_validation_invalid_type_and_enum() -> None:
    registry = ToolRegistry()
    tool = DummySchemaTool()
    registry.register(tool)

    # Invalid type for count
    valid, err = registry.validate_parameters("dummy_tool", action="read", count="five")
    assert valid is False
    assert "Parameter 'count' must be of type integer" in err  # type: ignore[operator]

    # Invalid enum for action
    valid_enum, err_enum = registry.validate_parameters("dummy_tool", action="delete")
    assert valid_enum is False
    assert "not in allowed enum" in err_enum  # type: ignore[operator]


def test_tool_registry_nonexistent_tool() -> None:
    registry = ToolRegistry()
    valid, err = registry.validate_parameters("nonexistent", action="read")
    assert valid is False
    assert "not found in registry" in err  # type: ignore[operator]

    res = registry.execute("nonexistent")
    assert res.success is False
    assert "not found in registry" in res.error  # type: ignore[operator]
