"""Diagnostic and performance report generation for AURA."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from .manager import TelemetryManager

_PROCESS_BOOT_TIME = time.time()


def generate_runtime_report(
    db_path: str = "data/aura.db",
    filepath: str | Path = "diagnostics/runtime_report.json",
) -> dict[str, Any]:
    """Generates and writes a comprehensive runtime report to JSON."""
    uptime_sec = round(time.time() - _PROCESS_BOOT_TIME, 2)

    # Memory & CPU metrics with psutil / fallback
    memory_rss_mb = 0.0
    cpu_percent = 0.0
    try:
        import psutil

        proc = psutil.Process(os.getpid())
        memory_rss_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
        cpu_percent = round(proc.cpu_percent(interval=0.0), 2)
    except Exception:
        pass

    # SQLite metrics
    db_file_path = Path(db_path)
    sqlite_db_size = db_file_path.stat().st_size if db_file_path.exists() else 0

    wal_file_path = Path(f"{db_path}-wal")
    sqlite_wal_size = wal_file_path.stat().st_size if wal_file_path.exists() else 0

    page_count = 0
    page_size = 0
    if db_file_path.exists():
        try:
            conn = sqlite3.connect(str(db_file_path))
            cur = conn.execute("PRAGMA page_count;")
            page_count = cur.fetchone()[0]
            cur = conn.execute("PRAGMA page_size;")
            page_size = cur.fetchone()[0]
            conn.close()
        except Exception:
            pass

    tm = TelemetryManager.get_instance()
    telemetry_counters = tm.get_all_counters()

    report_data: dict[str, Any] = {
        "uptime_seconds": uptime_sec,
        "cpu_percent": cpu_percent,
        "memory_rss_mb": memory_rss_mb,
        "sqlite_db_size_bytes": sqlite_db_size,
        "sqlite_page_count": page_count,
        "sqlite_page_size": page_size,
        "sqlite_wal_size_bytes": sqlite_wal_size,
        "telemetry_counters": telemetry_counters,
    }

    out_path = Path(filepath)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    return report_data
