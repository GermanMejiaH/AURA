"""Database Backup Utility — AURA 1.6 Stage 24.

Provides verifiable physical backup creation, checksum validation,
and deterministic rollback restoration for SQLite databases.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime
from typing import Any

from aura.logging import get_logger

logger = get_logger("DatabaseBackupManager")


class DatabaseBackupManager:
    """Manages physical backup and restoration of SQLite database files."""

    def __init__(self, db_path: str) -> None:
        self.db_path = os.path.abspath(db_path)

    @staticmethod
    def compute_sha256(file_path: str) -> str:
        """Computes the SHA-256 hash of a file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def create_backup(self) -> dict[str, Any]:
        """Creates a timestamped physical backup of the target database file.

        Returns metadata dictionary containing backup path, timestamp, and checksums.
        """
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database file does not exist: {self.db_path}")

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.dirname(self.db_path)
        base_name = os.path.basename(self.db_path)
        backup_name = f"{base_name}.bak_{timestamp}"
        backup_path = os.path.join(backup_dir, backup_name)

        original_hash = self.compute_sha256(self.db_path)
        shutil.copy2(self.db_path, backup_path)
        backup_hash = self.compute_sha256(backup_path)

        if original_hash != backup_hash:
            os.remove(backup_path)
            raise RuntimeError(
                f"Backup copy verification failed for '{self.db_path}'. Checksums do not match!"
            )

        logger.info(
            f"Verifiable physical database backup created at '{backup_path}' "
            f"[SHA256: {backup_hash[:12]}]"
        )

        return {
            "original_path": self.db_path,
            "backup_path": backup_path,
            "timestamp": timestamp,
            "sha256": backup_hash,
            "size_bytes": os.path.getsize(backup_path),
        }

    def restore_backup(self, backup_path: str) -> bool:
        """Restores the target database from a verified physical backup file."""
        backup_path = os.path.abspath(backup_path)
        if not os.path.exists(backup_path):
            logger.error(f"Backup file not found for restoration: '{backup_path}'")
            return False

        try:
            shutil.copy2(backup_path, self.db_path)
            logger.info(f"Database restored successfully from backup '{backup_path}'")
        except Exception as exc:
            logger.error(f"Failed to restore database from backup '{backup_path}': {exc}")
            return False
        else:
            return True
