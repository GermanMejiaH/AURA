from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolMetadata, ToolResult


class RealSandboxedFileTool(BaseTool):
    """Built-in tool for sandboxed file operations strictly confined to a sandbox directory."""

    metadata = ToolMetadata(
        name="real_sandboxed_file_tool",
        description="Reads, writes, lists, and checks existence of files within a safe sandbox",
        category="system",
        parameters_schema={
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "list", "exists"],
                },
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
        },
        risk_level="reversible",
        requires_confirmation=False,
        read_only=False,
    )

    MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB limit

    def __init__(self, sandbox_root: str | Path | None = None) -> None:
        if sandbox_root is not None:
            self._sandbox_root = Path(sandbox_root).resolve()
        else:
            self._sandbox_root = (Path.cwd() / "data" / "sandbox").resolve()

        self._sandbox_root.mkdir(parents=True, exist_ok=True)

    @property
    def sandbox_root(self) -> Path:
        return self._sandbox_root

    def _resolve_and_validate_path(self, target_path_str: str) -> Path | str:
        """Resolves target_path_str relative to sandbox_root and validates containment."""
        if not target_path_str or not target_path_str.strip():
            return self._sandbox_root

        try:
            clean_str = target_path_str.lstrip("/\\")
            target_path = Path(clean_str)

            if target_path.is_absolute():
                resolved = target_path.resolve()
            else:
                resolved = (self._sandbox_root / target_path).resolve()

            sandbox_resolved = self._sandbox_root.resolve()
            if not self._is_contained(resolved, sandbox_resolved):
                return (
                    f"Path traversal security violation: '{target_path_str}' "
                    f"escapes sandbox directory '{self._sandbox_root}'"
                )
        except Exception as exc:
            return f"Invalid path resolution for '{target_path_str}': {exc}"
        else:
            return resolved

    @staticmethod
    def _is_contained(path: Path, root: Path) -> bool:
        """Verifies that path is inside root directory."""
        try:
            if hasattr(path, "is_relative_to"):
                return path.is_relative_to(root)
            common = os.path.commonpath([str(path), str(root)])
            return common == str(root)
        except ValueError, TypeError:
            return False

    def execute(
        self,
        action: str = "read",
        path: str = "",
        content: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        t0 = time.perf_counter()
        normalized_action = action.lower().strip() if action else "read"

        valid_actions = {"read", "write", "list", "exists"}
        if normalized_action not in valid_actions:
            return ToolResult(
                success=False,
                error=f"Unsupported file action '{action}'. Valid actions: {sorted(valid_actions)}",
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )

        resolved_or_err = self._resolve_and_validate_path(path)
        if isinstance(resolved_or_err, str):
            return ToolResult(
                success=False,
                error=resolved_or_err,
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )

        target_path = resolved_or_err

        try:
            if normalized_action == "exists":
                exists_flag = target_path.exists()
                return ToolResult(
                    success=True,
                    output={
                        "path": str(target_path.relative_to(self._sandbox_root)),
                        "exists": exists_flag,
                    },
                    execution_time_ms=(time.perf_counter() - t0) * 1000,
                )

            elif normalized_action == "list":
                dir_path = target_path if target_path.is_dir() else target_path.parent
                if not dir_path.exists():
                    return ToolResult(
                        success=False,
                        error=f"Directory '{path}' does not exist",
                        execution_time_ms=(time.perf_counter() - t0) * 1000,
                    )
                entries = []
                for entry in sorted(dir_path.iterdir()):
                    if self._is_contained(entry.resolve(), self._sandbox_root):
                        rel = entry.relative_to(self._sandbox_root)
                        entries.append(str(rel) + ("/" if entry.is_dir() else ""))
                return ToolResult(
                    success=True,
                    output={
                        "directory": str(dir_path.relative_to(self._sandbox_root)),
                        "items": entries,
                    },
                    execution_time_ms=(time.perf_counter() - t0) * 1000,
                )

            elif normalized_action == "read":
                if not target_path.exists():
                    return ToolResult(
                        success=False,
                        error=f"File '{path}' does not exist in sandbox",
                        execution_time_ms=(time.perf_counter() - t0) * 1000,
                    )
                if target_path.is_dir():
                    return ToolResult(
                        success=False,
                        error=f"Path '{path}' is a directory, not a file",
                        execution_time_ms=(time.perf_counter() - t0) * 1000,
                    )
                file_size = target_path.stat().st_size
                if file_size > self.MAX_FILE_SIZE_BYTES:
                    err_msg = (
                        f"File '{path}' size ({file_size} bytes) "
                        f"exceeds limit ({self.MAX_FILE_SIZE_BYTES} bytes)"
                    )
                    return ToolResult(
                        success=False,
                        error=err_msg,
                        execution_time_ms=(time.perf_counter() - t0) * 1000,
                    )
                text_content = target_path.read_text(encoding="utf-8", errors="replace")
                return ToolResult(
                    success=True,
                    output={
                        "path": str(target_path.relative_to(self._sandbox_root)),
                        "content": text_content,
                        "size_bytes": file_size,
                    },
                    execution_time_ms=(time.perf_counter() - t0) * 1000,
                )

            elif normalized_action == "write":
                content_bytes = content.encode("utf-8")
                if len(content_bytes) > self.MAX_FILE_SIZE_BYTES:
                    err_msg = (
                        f"Content size ({len(content_bytes)} bytes) "
                        f"exceeds limit ({self.MAX_FILE_SIZE_BYTES} bytes)"
                    )
                    return ToolResult(
                        success=False,
                        error=err_msg,
                        execution_time_ms=(time.perf_counter() - t0) * 1000,
                    )
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content, encoding="utf-8")
                return ToolResult(
                    success=True,
                    output={
                        "path": str(target_path.relative_to(self._sandbox_root)),
                        "bytes_written": len(content_bytes),
                    },
                    execution_time_ms=(time.perf_counter() - t0) * 1000,
                )

            return ToolResult(
                success=False,
                error=f"Unhandled action '{action}'",
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )

        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"File operation failed: {exc}",
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )
