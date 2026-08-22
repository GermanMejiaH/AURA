from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class ConfigValue(Generic[T]):
    value: T
    source: str = "default"
    mutable: bool = True


@dataclass
class ConfigurationManager:
    _values: dict[str, ConfigValue[Any]] = field(default_factory=dict)
    _sources: list[str] = field(default_factory=list)
    _loaded: bool = False

    def __post_init__(self) -> None:
        self._register_defaults()

    def _register_defaults(self) -> None:
        defaults: dict[str, tuple[Any, str]] = {
            "system.name": ("AURA", "default"),
            "system.version": ("0.1.0", "default"),
            "system.environment": ("development", "default"),
            "system.timezone": ("UTC", "default"),
            "logging.level": ("INFO", "default"),
            "logging.format": ("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "default"),
            "logging.enable_file": (False, "default"),
            "logging.file_path": ("aura.log", "default"),
            "event_bus.max_history": (1000, "default"),
            "event_bus.publish_global": (True, "default"),
            "health.check_interval_sec": (30, "default"),
            "health.enabled": (True, "default"),
            "scheduler.max_workers": (4, "default"),
            "scheduler.enabled": (True, "default"),
            "modules.auto_discover": (False, "default"),
            "modules.search_paths": (["aura.modules"], "default"),
            "core.boot_timeout_sec": (30, "default"),
            "core.shutdown_timeout_sec": (15, "default"),
            "audio.input_device": ("C920", "default"),
            "audio.target_sample_rate": (16000, "default"),
            "audio.input_channels": (1, "default"),
            "autonomy.enabled": (True, "default"),
            "autonomy.tick_interval_seconds": (1.0, "default"),
            "autonomy.runtime_enabled": (True, "default"),
            "autonomy.health_monitoring_enabled": (True, "default"),
            "autonomy.self_recovery_enabled": (True, "default"),
            "autonomy.recovery_max_attempts": (3, "default"),
            "autonomy.recovery_backoff_seconds": (30.0, "default"),
            "autonomy.persistence_enabled": (True, "default"),
            "autonomy.history_max_events": (1000, "default"),
            "autonomy.history_retention_days": (30, "default"),
            "autonomy.diagnostics_enabled": (True, "default"),
            "autonomy.diagnostics_history_size": (50, "default"),
            "autonomy.adaptation_enabled": (True, "default"),
            "autonomy.min_tick_interval_seconds": (0.05, "default"),
            "autonomy.max_tick_interval_seconds": (60.0, "default"),
            "autonomy.reduced_activity_multiplier": (2.0, "default"),
            "autonomy.control_enabled": (True, "default"),
            "autonomy.control_history_size": (100, "default"),
            "autonomy.state_persistence_enabled": (True, "default"),
            "autonomy.state_recovery_enabled": (True, "default"),
            "autonomy.governance_enabled": (True, "default"),
            "autonomy.authority_scope": ("UNRESTRICTED", "default"),
            "autonomy.circuit_breaker_enabled": (True, "default"),
            "autonomy.circuit_failure_threshold": (5, "default"),
            "autonomy.circuit_cooloff_seconds": (60.0, "default"),
            "autonomy.rate_limit_max_calls_per_minute": (60, "default"),
            "autonomy.policy_resolution_enabled": (True, "default"),
            "autonomy.default_priority": ("NORMAL", "default"),
            "autonomy.priority_aging_enabled": (True, "default"),
            "autonomy.priority_aging_rate_per_minute": (1.0, "default"),
            "autonomy.max_aging_boost": (50.0, "default"),
            "autonomy.deadline_enforcement_enabled": (True, "default"),
            "autonomy.conflict_resolution_enabled": (True, "default"),
            "autonomy.execution_enabled": (True, "default"),
            "autonomy.execution_max_attempts": (3, "default"),
            "autonomy.execution_backoff_seconds": (1.0, "default"),
            "autonomy.execution_timeout_seconds": (30.0, "default"),
            "autonomy.execution_persistence_enabled": (True, "default"),
            "autonomy.execution_history_size": (100, "default"),
            "autonomy.execution_compensation_enabled": (True, "default"),
            "autonomy.experience_enabled": (True, "default"),
            "autonomy.experience_persistence_enabled": (True, "default"),
            "autonomy.experience_history_limit": (1000, "default"),
            "autonomy.experience_failure_threshold": (3, "default"),
            "autonomy.experience_timeout_threshold": (3, "default"),
            "autonomy.experience_review_threshold": (0.50, "default"),
            "autonomy.experience_recommendations_enabled": (True, "default"),
            "autonomy.adaptation_require_operator_approval": (True, "default"),
            "autonomy.adaptation_proposal_ttl_seconds": (3600, "default"),
            "autonomy.adaptation_max_frequency_change_percent": (50.0, "default"),
            "autonomy.adaptation_max_retry_attempts": (5, "default"),
            "autonomy.adaptation_auto_apply_enabled": (False, "default"),
            "autonomy.assurance_enabled": (True, "default"),
            "autonomy.assurance_health_interval_seconds": (30, "default"),
            "autonomy.assurance_checkpoint_enabled": (True, "default"),
            "autonomy.assurance_checkpoint_interval_seconds": (300, "default"),
            "autonomy.assurance_max_audit_records": (10000, "default"),
            "autonomy.assurance_safe_mode_enabled": (True, "default"),
            "autonomy.assurance_auto_recovery_enabled": (False, "default"),
            "autonomy.assurance_fail_closed": (True, "default"),
            "autonomy.orchestration_enabled": (True, "default"),
            "autonomy.orchestration_recovery_enabled": (True, "default"),
            "autonomy.orchestration_history_enabled": (True, "default"),
            "autonomy.orchestration_max_active_operations": (50, "default"),
        }
        for key, (value, source) in defaults.items():
            self._values[key] = ConfigValue(value=value, source=source, mutable=True)

    def load_from_dict(self, data: dict[str, Any], source: str = "dict") -> None:
        for key, value in self._flatten(data).items():
            existing = self._values.get(key)
            if existing is None or existing.mutable:
                self._values[key] = ConfigValue(value=value, source=source, mutable=True)
        if source not in self._sources:
            self._sources.append(source)

    def load_from_json(self, path: str | os.PathLike[str]) -> None:
        p = Path(path)
        if not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        self.load_from_dict(data, source=str(p))

    def load_from_env(self, prefix: str = "AURA_") -> None:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k and v:
                        os.environ[k] = v

        result: dict[str, Any] = {}
        for full_key, value in os.environ.items():
            if not full_key.startswith(prefix):
                continue
            key = full_key[len(prefix) :].lower().replace("__", ".")
            result[key] = self._coerce(value)
        if result:
            self.load_from_dict(result, source="environment")

    @staticmethod
    def _coerce(raw: str) -> Any:
        lowered = raw.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            return int(raw)
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            pass
        if raw.startswith("[") and raw.endswith("]"):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return raw

    @staticmethod
    def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        flat: dict[str, Any] = {}
        for key, value in data.items():
            full = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flat.update(ConfigurationManager._flatten(value, full))
            else:
                flat[full] = value
        return flat

    def get(self, key: str, default: T | None = None) -> Any:
        entry = self._values.get(key)
        if entry is None:
            return default
        return entry.value

    def get_typed(self, key: str, expected_type: type[T], default: T) -> T:
        value = self.get(key, default)
        if isinstance(value, expected_type):
            return value
        try:
            return expected_type(value)  # type: ignore[call-arg]
        except TypeError, ValueError:
            return default

    def set(self, key: str, value: Any, source: str = "runtime") -> None:
        existing = self._values.get(key)
        if existing is not None and not existing.mutable:
            raise ValueError(f"Config key '{key}' is immutable")
        self._values[key] = ConfigValue(value=value, source=source, mutable=True)

    def has(self, key: str) -> bool:
        return key in self._values

    def keys(self) -> list[str]:
        return sorted(self._values.keys())

    def items(self) -> Iterator[tuple[str, Any]]:
        for k, v in self._values.items():
            yield k, v.value

    def as_dict(self) -> dict[str, Any]:
        return {k: v.value for k, v in self._values.items()}

    def sources(self) -> list[str]:
        return list(self._sources)

    def mark_loaded(self) -> None:
        self._loaded = True

    @property
    def is_loaded(self) -> bool:
        return self._loaded
