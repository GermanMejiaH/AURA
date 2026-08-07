from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ..events import ErrorOccurred, EventBus, HealthCheckPerformed
from ..logging import get_logger
from ..modules.base import ModuleStatus

if TYPE_CHECKING:
    from ..config import ConfigurationManager
    from ..core.lifecycle import LifecycleManager
    from ..core.module_manager import ModuleManager
    from ..core.scheduler import Scheduler


@dataclass
class SystemHealth:
    overall: str = "healthy"
    started_at: datetime | None = None
    modules_total: int = 0
    modules_healthy: int = 0
    modules_degraded: int = 0
    modules_failed: int = 0
    last_check_at: datetime | None = None
    issues: list[str] = field(default_factory=list)


@dataclass
class HealthMonitor:
    module_manager: ModuleManager | None = None
    lifecycle: LifecycleManager | None = None
    event_bus: EventBus | None = None
    config: ConfigurationManager | None = None
    scheduler: Scheduler | None = None

    _last_result: SystemHealth = field(default_factory=SystemHealth)
    _job_id: object = None
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _running: bool = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        logger = get_logger("HealthMonitor")
        interval = (
            self.config.get_typed("health.check_interval_sec", int, 30)
            if self.config is not None
            else 30
        )
        enabled = (
            self.config.get_typed("health.enabled", bool, True) if self.config is not None else True
        )
        if enabled and self.scheduler is not None:
            self._job_id = self.scheduler.schedule_periodic(
                "health_check",
                self.perform_check,
                interval=interval,
                start=datetime.now(UTC),
            )
        logger.info(f"HealthMonitor started (interval={interval}s, enabled={enabled})")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self.scheduler is not None and self._job_id is not None:
            try:
                from uuid import UUID

                if isinstance(self._job_id, UUID):
                    self.scheduler.cancel(self._job_id)
            except Exception:
                pass
        logger = get_logger("HealthMonitor")
        logger.info("HealthMonitor stopped")

    @property
    def last_result(self) -> SystemHealth:
        return SystemHealth(
            overall=self._last_result.overall,
            started_at=self._last_result.started_at,
            modules_total=self._last_result.modules_total,
            modules_healthy=self._last_result.modules_healthy,
            modules_degraded=self._last_result.modules_degraded,
            modules_failed=self._last_result.modules_failed,
            last_check_at=self._last_result.last_check_at,
            issues=list(self._last_result.issues),
        )

    def perform_check(self) -> SystemHealth:
        with self._lock:
            logger = get_logger("HealthMonitor")
            logger.debug("Running health check")

            issues: list[str] = []
            healthy = 0
            degraded = 0
            failed = 0
            total = 0

            if self.module_manager is not None:
                for name, module in self.module_manager.list_modules():
                    total += 1
                    try:
                        snapshot = module.check_health()
                    except Exception as exc:
                        failed += 1
                        issues.append(f"{name}: health check exception: {exc}")
                        continue
                    status = snapshot.status
                    if status in {ModuleStatus.RUNNING, ModuleStatus.READY}:
                        healthy += 1
                    elif status in {ModuleStatus.DEGRADED, ModuleStatus.PAUSED}:
                        degraded += 1
                        issues.append(f"{name}: status={status.value}")
                    elif status in {
                        ModuleStatus.ERROR,
                        ModuleStatus.STOPPING,
                        ModuleStatus.STOPPED,
                        ModuleStatus.UNLOADED,
                    }:
                        failed += 1
                        msg = f"{name}: status={status.value}"
                        if snapshot.last_error:
                            msg += f" - {snapshot.last_error}"
                        issues.append(msg)
                        if self.event_bus is not None:
                            try:
                                self.event_bus.publish(
                                    ErrorOccurred(
                                        source="HealthMonitor",
                                        module=name,
                                        error_type="unhealthy_module",
                                        error_message=msg,
                                        recoverable=True,
                                    )
                                )
                            except Exception:
                                pass

            overall = "healthy"
            if failed > 0:
                overall = "unhealthy"
            elif degraded > 0:
                overall = "degraded"

            if self.lifecycle is not None and self.lifecycle._boot_time is not None:
                started_at: datetime | None = self.lifecycle._boot_time
            else:
                started_at = self._last_result.started_at

            result = SystemHealth(
                overall=overall,
                started_at=started_at,
                modules_total=total,
                modules_healthy=healthy,
                modules_degraded=degraded,
                modules_failed=failed,
                last_check_at=datetime.now(UTC),
                issues=issues,
            )
            self._last_result = result

            if self.event_bus is not None:
                try:
                    self.event_bus.publish(
                        HealthCheckPerformed(
                            source="HealthMonitor",
                            overall_status=overall,
                            modules_checked=total,
                            modules_healthy=healthy,
                        )
                    )
                except Exception:
                    pass

            if overall != "healthy":
                msg = (
                    f"Health check: {overall} "
                    f"(healthy={healthy}, degraded={degraded}, failed={failed})"
                )
                logger.warning(msg)
            else:
                logger.debug(f"Health check: {overall} ({healthy}/{total} modules)")

            return result
