from __future__ import annotations

import os
import platform
import time
from typing import Any

import psutil

from .base import BaseTool, ToolMetadata, ToolResult


class RealSystemObservationTool(BaseTool):
    """Built-in tool for observing real host OS metrics (CPU, memory, disk, platform)."""

    metadata = ToolMetadata(
        name="real_system_observation_tool",
        description="Queries real host OS system metrics (CPU, memory, disk, platform, processes)",
        category="system",
        parameters_schema={
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["cpu", "memory", "disk", "platform", "processes", "network", "all"],
                }
            }
        },
        risk_level="safe",
        requires_confirmation=False,
        read_only=True,
    )

    def execute(self, action: str = "all", **kwargs: Any) -> ToolResult:
        t0 = time.perf_counter()
        normalized_action = action.lower().strip() if action else "all"

        valid_actions = {"cpu", "memory", "disk", "platform", "processes", "network", "all"}
        if normalized_action not in valid_actions:
            err_msg = (
                f"Unsupported system observation action '{action}'. "
                f"Valid actions: {sorted(valid_actions)}"
            )
            return ToolResult(
                success=False,
                error=err_msg,
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )

        data: dict[str, Any] = {}

        try:
            if normalized_action in ("cpu", "all"):
                data["cpu"] = self._get_cpu_metrics()

            if normalized_action in ("memory", "all"):
                data["memory"] = self._get_memory_metrics()

            if normalized_action in ("disk", "all"):
                data["disk"] = self._get_disk_metrics()

            if normalized_action in ("platform", "all"):
                data["platform"] = self._get_platform_metrics()

            if normalized_action in ("processes", "all"):
                data["processes"] = self._get_process_metrics()

            if normalized_action in ("network", "all"):
                data["network"] = self._get_network_metrics()

            elapsed = (time.perf_counter() - t0) * 1000
            output_result = data[normalized_action] if normalized_action != "all" else data
            return ToolResult(success=True, output=output_result, execution_time_ms=elapsed)

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            return ToolResult(
                success=False,
                error=f"Error querying host system metrics: {exc}",
                execution_time_ms=elapsed,
            )

    def _get_cpu_metrics(self) -> dict[str, Any]:
        try:
            percent = psutil.cpu_percent(interval=None)
            count = os.cpu_count() or 1
            return {"cpu_percent": float(percent), "cpu_count": count}
        except Exception:
            return {"cpu_percent": 0.0, "cpu_count": os.cpu_count() or 1}

    def _get_memory_metrics(self) -> dict[str, Any]:
        try:
            mem = psutil.virtual_memory()
            return {
                "memory_available_mb": round(mem.available / (1024 * 1024), 2),
                "memory_total_mb": round(mem.total / (1024 * 1024), 2),
                "memory_percent": float(mem.percent),
            }
        except Exception:
            return {"memory_available_mb": 0.0, "memory_total_mb": 0.0, "memory_percent": 0.0}

    def _get_disk_metrics(self) -> dict[str, Any]:
        try:
            root_path = "C:\\" if os.name == "nt" else "/"
            disk = psutil.disk_usage(root_path)
            return {
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "disk_percent": float(disk.percent),
            }
        except Exception:
            return {"disk_free_gb": 0.0, "disk_total_gb": 0.0, "disk_percent": 0.0}

    def _get_platform_metrics(self) -> dict[str, Any]:
        try:
            return {
                "platform_info": f"{platform.system()} {platform.release()} ({platform.machine()})",
                "python_version": platform.python_version(),
                "system": platform.system(),
            }
        except Exception:
            return {
                "platform_info": "Unknown OS",
                "python_version": platform.python_version(),
                "system": "Unknown",
            }

    def _get_process_metrics(self) -> dict[str, Any]:
        try:
            count = len(psutil.pids())
        except Exception:
            count = 0
        return {"active_process_count": count}

    def _get_network_metrics(self) -> dict[str, Any]:
        try:
            net_io = psutil.net_io_counters()
            if net_io is not None:
                return {
                    "bytes_sent": net_io.bytes_sent,
                    "bytes_recv": net_io.bytes_recv,
                    "network_connected": True,
                }
        except Exception:
            pass
        return {"bytes_sent": 0, "bytes_recv": 0, "network_connected": False}
