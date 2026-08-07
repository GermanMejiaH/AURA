from __future__ import annotations

from aura.tools import (
    APITool,
    BrowserTool,
    CalendarTool,
    EmailTool,
    FileTool,
    SpotifyTool,
)


def test_builtin_tools_execution():
    file_tool = FileTool()
    assert file_tool.execute(action="read", path="test.txt").success is True
    assert file_tool.execute(action="write", path="test.txt", content="hi").success is True
    assert file_tool.execute(action="list").success is True

    browser_tool = BrowserTool()
    assert browser_tool.execute(url="https://aura.ai").success is True

    cal_tool = CalendarTool()
    assert cal_tool.execute(title="Meeting").success is True

    spotify_tool = SpotifyTool()
    assert spotify_tool.execute(action="play", track="Song").success is True

    email_tool = EmailTool()
    assert email_tool.execute(to="test@aura.ai", subject="Hi").success is True

    api_tool = APITool()
    assert api_tool.execute(method="GET", url="https://api.aura.ai").success is True
