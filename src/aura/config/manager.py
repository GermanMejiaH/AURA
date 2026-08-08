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
            "modules.auto_discover": (True, "default"),
            "modules.search_paths": (["aura.modules"], "default"),
            "core.boot_timeout_sec": (30, "default"),
            "core.shutdown_timeout_sec": (15, "default"),
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
        except (TypeError, ValueError):
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
