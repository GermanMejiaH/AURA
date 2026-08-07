from __future__ import annotations

from typing import Any

from .base import BaseTool, ToolMetadata, ToolResult


class FileTool(BaseTool):
    """Built-in tool for file operations (read, write, list)."""

    metadata = ToolMetadata(
        name="file_tool",
        description="Reads, writes and lists files in workspace",
        category="system",
    )

    def execute(
        self,
        action: str = "read",
        path: str = "",
        content: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        if action == "read":
            return ToolResult(success=True, output=f"Content of {path}")
        elif action == "write":
            return ToolResult(success=True, output=f"Wrote {len(content)} bytes to {path}")
        elif action == "list":
            return ToolResult(success=True, output=["file1.txt", "file2.py"])
        return ToolResult(success=False, error=f"Unknown file action '{action}'")


class BrowserTool(BaseTool):
    """Built-in tool for browser navigation and web content extraction."""

    metadata = ToolMetadata(
        name="browser_tool",
        description="Simulates web browsing and page content extraction",
        category="web",
    )

    def execute(
        self,
        url: str = "https://example.com",
        target: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        target_url = target or url
        return ToolResult(success=True, output=f"Extracted content from {target_url}")


class CalendarTool(BaseTool):
    """Built-in tool for managing calendar events and reminders."""

    metadata = ToolMetadata(
        name="calendar_tool",
        description="Manages calendar events and reminders",
        category="productivity",
    )

    def execute(
        self,
        action: str = "create_event",
        title: str = "Reunión",
        date: str = "2026-08-08",
        **kwargs: Any,
    ) -> ToolResult:
        return ToolResult(success=True, output=f"Event '{title}' scheduled on {date}")


class SpotifyTool(BaseTool):
    """Built-in tool for media playback control."""

    metadata = ToolMetadata(
        name="spotify_tool",
        description="Controls music playback on Spotify",
        category="media",
    )

    def execute(self, action: str = "play", track: str = "", **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output=f"Spotify action '{action}' executed for '{track}'")


class EmailTool(BaseTool):
    """Built-in tool for sending and reading emails."""

    metadata = ToolMetadata(
        name="email_tool",
        description="Sends and reads emails",
        category="communication",
    )

    def execute(
        self,
        action: str = "send",
        to: str = "",
        subject: str = "",
        body: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        return ToolResult(success=True, output=f"Email sent to {to} with subject '{subject}'")


class APITool(BaseTool):
    """Built-in tool for generic REST API HTTP requests."""

    metadata = ToolMetadata(
        name="api_tool",
        description="Executes generic REST API HTTP requests",
        category="network",
    )

    def execute(
        self,
        method: str = "GET",
        url: str = "",
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        return ToolResult(success=True, output={"status": 200, "data": "OK"})
