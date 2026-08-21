from __future__ import annotations

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import Event, EventBus
from ..logging import get_logger
from ..modules.base import BaseModule
from .builtins import (
    APITool,
    BrowserTool,
    CalculatorTool,
    CalendarTool,
    DateTimeTool,
    EmailTool,
    FileTool,
    SpotifyTool,
    SystemStatusTool,
)
from .http_retrieval_tool import RealHTTPRetrievalTool
from .registry import ToolRegistry
from .sandboxed_file_tool import RealSandboxedFileTool
from .system_observation import RealSystemObservationTool


class ToolsModule(BaseModule):
    """Core module responsible for external tools registration, dispatch & execution."""

    name = "tools"
    description = "Tools System - External App Control & Registry Dispatch"
    priority = 40

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        container: DependencyContainer | None = None,
        event_bus: EventBus | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        super().__init__(config, container, event_bus)
        self.registry = registry if registry is not None else ToolRegistry()

    def on_initialize(self) -> None:
        logger = get_logger("ToolsModule")

        # Register built-in tools
        self.registry.register(FileTool())
        self.registry.register(BrowserTool())
        self.registry.register(CalendarTool())
        self.registry.register(SpotifyTool())
        self.registry.register(EmailTool())
        self.registry.register(APITool())
        self.registry.register(DateTimeTool())
        self.registry.register(CalculatorTool())
        self.registry.register(SystemStatusTool())
        self.registry.register(RealSystemObservationTool())
        self.registry.register(RealSandboxedFileTool())
        self.registry.register(RealHTTPRetrievalTool())

        # Register IoC instances
        if self._container is not None:
            self._container.register(ToolRegistry, instance=self.registry)

        # Subscriptions
        self.subscribe("ActionDispatched", self._on_action_dispatched)

        count = len(self.registry.list_metadata())
        logger.info(f"ToolsModule initialized ({count} tools registered)")

    def _on_action_dispatched(self, event: Event) -> None:
        action_type = getattr(event, "action_type", "") or event.payload.get("action_type", "")
        target = getattr(event, "target", "") or event.payload.get("target", "")

        # Try to dispatch to matching tool
        tool = self.registry.get(action_type) or self.registry.get(f"{action_type}_tool")
        if tool is not None:
            res = self.registry.execute(tool.metadata.name, target=target)
            if self._event_bus is not None:
                if res.success:
                    from ..events import ToolExecuted

                    self.publish(
                        ToolExecuted(
                            source="ToolsModule",
                            tool_name=tool.metadata.name,
                            success=True,
                            execution_time_ms=res.execution_time_ms,
                        )
                    )
                else:
                    from ..events import ToolFailed

                    self.publish(
                        ToolFailed(
                            source="ToolsModule",
                            tool_name=tool.metadata.name,
                            error=res.error or "Unknown tool error",
                        )
                    )
