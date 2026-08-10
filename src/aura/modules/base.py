from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import ConfigurationManager
    from ..container import DependencyContainer
    from ..events import EventBus


class ModuleStatus(str, Enum):
    UNLOADED = "Unloaded"
    LOADED = "Loaded"
    INITIALIZING = "Initializing"
    READY = "Ready"
    RUNNING = "Running"
    PAUSED = "Paused"
    STOPPING = "Stopping"
    STOPPED = "Stopped"
    ERROR = "Error"
    DEGRADED = "Degraded"


@dataclass
class ModuleHealth:
    status: ModuleStatus = ModuleStatus.UNLOADED
    last_error: str | None = None
    started_at: str | None = None
    memory_usage_bytes: int = 0
    metrics: dict[str, object] = field(default_factory=dict)


class BaseModule(ABC):
    name: str = "base-module"
    version: str = "0.1.0"
    description: str = ""
    priority: int = 100
    required: bool = False

    def __init__(
        self,
        config: ConfigurationManager | None = None,
        container: DependencyContainer | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._config = config
        self._container = container
        self._event_bus = event_bus
        self._health = ModuleHealth()
        self._initialized = False

    @property
    def health(self) -> ModuleHealth:
        return ModuleHealth(
            status=self._health.status,
            last_error=self._health.last_error,
            started_at=self._health.started_at,
            memory_usage_bytes=self._health.memory_usage_bytes,
            metrics=dict(self._health.metrics),
        )

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def set_status(self, status: ModuleStatus, error: str | None = None) -> None:
        self._health.status = status
        if error is not None:
            self._health.last_error = error

    def load(self) -> None:
        try:
            self.on_load()
            self._health.status = ModuleStatus.LOADED
        except Exception as exc:
            self._health.status = ModuleStatus.ERROR
            self._health.last_error = str(exc)
            raise

    def initialize(self) -> None:
        self._health.status = ModuleStatus.INITIALIZING
        try:
            self.on_initialize()
            self._initialized = True
            self._health.status = ModuleStatus.READY
        except Exception as exc:
            self._initialized = False
            self._health.status = ModuleStatus.ERROR
            self._health.last_error = str(exc)
            raise

    def start(self) -> None:
        from datetime import datetime

        try:
            self.on_start()
            self._health.status = ModuleStatus.RUNNING
            self._health.started_at = datetime.now(UTC).isoformat()
        except Exception as exc:
            self._health.status = ModuleStatus.ERROR
            self._health.last_error = str(exc)
            raise

    def pause(self) -> None:
        try:
            self.on_pause()
            self._health.status = ModuleStatus.PAUSED
        except Exception as exc:
            self._health.status = ModuleStatus.ERROR
            self._health.last_error = str(exc)
            raise

    def resume(self) -> None:
        try:
            self.on_resume()
            self._health.status = ModuleStatus.RUNNING
        except Exception as exc:
            self._health.status = ModuleStatus.ERROR
            self._health.last_error = str(exc)
            raise

    def stop(self) -> None:
        self._health.status = ModuleStatus.STOPPING
        try:
            self.on_stop()
            self._health.status = ModuleStatus.STOPPED
        except Exception as exc:
            self._health.status = ModuleStatus.ERROR
            self._health.last_error = str(exc)
            raise

    def shutdown(self) -> None:
        active = {
            ModuleStatus.RUNNING,
            ModuleStatus.PAUSED,
            ModuleStatus.DEGRADED,
            ModuleStatus.STOPPING,
        }
        stop_exc: Exception | None = None
        if self._health.status in active:
            try:
                self.stop()
            except Exception as exc:
                stop_exc = exc
        try:
            self.on_shutdown()
        except Exception as exc:
            if stop_exc is None:
                stop_exc = exc
        if stop_exc is not None:
            self._health.status = ModuleStatus.ERROR
            self._health.last_error = str(stop_exc)
            raise stop_exc

    def check_health(self) -> ModuleHealth:
        try:
            custom = self.on_health_check()
            if custom is not None:
                self._health.metrics.update(custom)
        except Exception as exc:
            self._health.status = ModuleStatus.ERROR
            self._health.last_error = str(exc)
        return self.health

    def on_load(self) -> None:
        pass

    @abstractmethod
    def on_initialize(self) -> None:
        ...

    def on_start(self) -> None:
        pass

    def on_pause(self) -> None:
        pass

    def on_resume(self) -> None:
        pass

    def on_stop(self) -> None:
        pass

    def on_shutdown(self) -> None:
        pass

    def publish(self, event: object) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(event)  # type: ignore[arg-type]

    def subscribe(self, event_type: type[object] | str, handler: object) -> None:
        if self._event_bus is not None:
            self._event_bus.subscribe(event_type, handler)  # type: ignore[arg-type]

    def on_health_check(self) -> dict[str, object] | None:
        return None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name} status={self._health.status.value}>"
