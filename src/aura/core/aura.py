from __future__ import annotations

import os
import signal
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..diagnostics import Diagnostics
from ..events import (
    ConfigLoaded,
    Event,
    EventBus,
    SystemBooting,
    SystemInitialized,
    SystemReady,
    SystemShutdownRequested,
    SystemShuttingDown,
    SystemStopped,
)
from ..health import HealthMonitor
from ..logging import (
    AuraLogger,
    configure_logging,
    get_logger,
    set_logger_instance,
)
from ..logging import (
    attach_event_bus as attach_log_to_bus,
)
from ..modules.base import BaseModule
from .lifecycle import LifecycleManager, SystemState
from .module_manager import ModuleManager
from .scheduler import Scheduler


@dataclass
class AURABootOptions:
    config_paths: Sequence[str | os.PathLike[str]] = ()
    load_env: bool = True
    env_prefix: str = "AURA_"
    log_level: str = "INFO"
    log_format: str | None = None
    log_to_file: bool = False
    log_file_path: str = "aura.log"
    enable_scheduler: bool = True
    enable_health_monitor: bool = True
    auto_discover_modules: bool = False
    module_classes: Sequence[type[BaseModule]] = ()
    graceful_shutdown_timeout: float = 15.0


@dataclass
class AURA:
    options: AURABootOptions = field(default_factory=AURABootOptions)

    config: ConfigurationManager = field(default_factory=ConfigurationManager)
    container: DependencyContainer = field(default_factory=DependencyContainer)
    event_bus: EventBus = field(default_factory=EventBus)
    logger_root: AuraLogger = field(default_factory=AuraLogger)
    lifecycle: LifecycleManager = field(default_factory=LifecycleManager)
    module_manager: ModuleManager | None = None
    scheduler: Scheduler | None = None
    health_monitor: HealthMonitor | None = None
    diagnostics: Diagnostics = field(default_factory=Diagnostics)

    _shutdown_event: threading.Event = field(default_factory=threading.Event)
    _boot_lock: threading.RLock = field(default_factory=threading.RLock)
    _booted: bool = False
    _signal_handlers_installed: bool = False

    def __post_init__(self) -> None:
        set_logger_instance(self.logger_root)
        self.diagnostics.event_bus = self.event_bus
        self.diagnostics.lifecycle = self.lifecycle

    # ---------------------------------------------------------
    # Boot / Shutdown
    # ---------------------------------------------------------
    def boot(self, options: AURABootOptions | None = None) -> AURA:
        with self._boot_lock:
            if self._booted:
                return self
            if options is not None:
                self.options = options

            self.diagnostics.mark_boot_started()

            self._step1_bootstrap_logging()
            self._step2_load_configuration()
            self._step3_register_core_services()
            self._step4_build_support_components()
            self._step5_lifecycle_boot()
            self._step6_discover_and_load_modules()
            self._step7_initialize_and_start()
            self._step8_become_ready()

            self._booted = True
            self._install_signal_handlers()
            return self

    def run_until_shutdown(self, poll_interval: float = 0.5) -> None:
        if not self._booted:
            self.boot()
        logger = get_logger("AURA")
        logger.info("AURA running. Waiting for shutdown signal...")
        try:
            while not self._shutdown_event.is_set():
                time.sleep(poll_interval)
        finally:
            if self.lifecycle.is_running or self.lifecycle.is_booting:
                self.shutdown(wait=True)

    def request_shutdown(self, reason: str = "manual") -> None:
        logger = get_logger("AURA")
        logger.info(f"Shutdown requested: {reason}")
        try:
            self.event_bus.publish(
                SystemShutdownRequested(source="AURA", reason=reason)
            )
        except Exception:
            pass
        self._shutdown_event.set()

    def shutdown(self, *, wait: bool = False, timeout: float | None = None) -> bool:
        with self._boot_lock:
            if not self._booted and self.lifecycle.is_stopped:
                return True
            self._shutdown_event.set()
            self.diagnostics.mark_shutdown_started()
            logger = get_logger("AURA")
            grace = timeout if timeout is not None else self.options.graceful_shutdown_timeout

            try:
                self.lifecycle.begin_shutdown("shutdown_called")
                self.event_bus.publish(SystemShuttingDown(source="AURA"))
            except Exception:
                pass

            if self.health_monitor is not None:
                try:
                    self.health_monitor.stop()
                except Exception:
                    logger.exception("Failed to stop HealthMonitor")

            if self.scheduler is not None:
                try:
                    self.scheduler.stop(timeout=grace)
                except Exception:
                    logger.exception("Failed to stop Scheduler")

            if self.module_manager is not None:
                try:
                    self.module_manager.stop_all()
                except Exception:
                    logger.exception("Failed to stop modules")

            try:
                self.event_bus.publish(
                    SystemStopped(source="AURA", exit_code=0)
                )
            except Exception:
                pass

            try:
                self.lifecycle.stop("shutdown_complete")
            except Exception:
                pass

            self._booted = False
            logger.info("AURA shutdown complete")
            return True

    # ---------------------------------------------------------
    # Internal boot steps (SPEC-003 Ciclo de Arranque)
    # ---------------------------------------------------------
    def _step1_bootstrap_logging(self) -> None:
        opts = self.options
        self.logger_root.configure(
            level=opts.log_level,
            log_format=opts.log_format,
            enable_console=True,
            enable_file=opts.log_to_file,
            file_path=opts.log_file_path,
        )
        configure_logging(
            level=opts.log_level,
            log_format=opts.log_format,
            enable_file=opts.log_to_file,
            file_path=opts.log_file_path,
        )
        attach_log_to_bus(self.event_bus)
        logger = get_logger("AURA")
        logger.debug("Step 1/8: Logging bootstrapped")

    def _step2_load_configuration(self) -> None:
        for path in self.options.config_paths:
            try:
                self.config.load_from_json(path)
            except Exception:
                logger = get_logger("AURA")
                logger.exception(f"Failed to load config from {path}")
        if self.options.load_env:
            self.config.load_from_env(prefix=self.options.env_prefix)
        self.config.mark_loaded()
        try:
            self.event_bus.publish(
                ConfigLoaded(
                    source="boot",
                    config_keys=len(list(self.config.keys())),
                    payload={"sources": self.config.sources()},
                )
            )
        except Exception:
            pass
        logger = get_logger("AURA")
        key_count = len(list(self.config.keys()))
        sources = self.config.sources()
        logger.debug(f"Step 2/8: Configuration loaded ({key_count} keys, sources={sources})")

    def _step3_register_core_services(self) -> None:
        self.container.register(ConfigurationManager, instance=self.config)
        self.container.register(DependencyContainer, instance=self.container)
        self.container.register(EventBus, instance=self.event_bus)
        self.container.register(LifecycleManager, instance=self.lifecycle)
        self.container.register(AuraLogger, instance=self.logger_root)
        self.container.register(Diagnostics, instance=self.diagnostics)
        self.event_bus.publish(SystemBooting(source="AURA"))
        logger = get_logger("AURA")
        logger.debug("Step 3/8: Core services registered in IoC container")

    def _step4_build_support_components(self) -> None:
        self.module_manager = ModuleManager(
            config=self.config,
            container=self.container,
            event_bus=self.event_bus,
            lifecycle=self.lifecycle,
        )
        self.container.register(ModuleManager, instance=self.module_manager)
        self.diagnostics.module_manager = self.module_manager

        if self.options.enable_scheduler or self.config.get_typed(
            "scheduler.enabled", bool, True
        ):
            self.scheduler = Scheduler(config=self.config)
            self.container.register(Scheduler, instance=self.scheduler)
            try:
                self.scheduler.start()
            except Exception:
                logger = get_logger("AURA")
                logger.exception("Failed to start Scheduler")

        self.health_monitor = HealthMonitor(
            module_manager=self.module_manager,
            lifecycle=self.lifecycle,
            event_bus=self.event_bus,
            config=self.config,
            scheduler=self.scheduler,
        )
        self.container.register(HealthMonitor, instance=self.health_monitor)
        if self.options.enable_health_monitor:
            try:
                self.health_monitor.start()
            except Exception:
                logger = get_logger("AURA")
                logger.exception("Failed to start HealthMonitor")

        self.event_bus.publish(SystemInitialized(source="AURA"))
        logger = get_logger("AURA")
        logger.debug("Step 4/8: Support components built (ModuleManager, Scheduler, HealthMonitor)")

    def _step5_lifecycle_boot(self) -> None:
        self.lifecycle.attach_bus(self.event_bus)
        self.lifecycle.boot()
        self.lifecycle.initialize()
        logger = get_logger("AURA")
        logger.debug(f"Step 5/8: Lifecycle booted -> {self.lifecycle.state.value}")

    def _step6_discover_and_load_modules(self) -> None:
        mm = self.module_manager
        assert mm is not None
        if self.options.module_classes:
            mm.register_many(list(self.options.module_classes))
        if self.options.auto_discover_modules or self.config.get_typed(
            "modules.auto_discover", bool, False
        ):
            try:
                mm.discover()
            except Exception:
                logger = get_logger("AURA")
                logger.exception("Module auto-discovery failed")
        logger = get_logger("AURA")
        logger.debug(f"Step 6/8: Modules loaded ({mm.count()} registered)")

    def _step7_initialize_and_start(self) -> None:
        mm = self.module_manager
        assert mm is not None
        init_results = mm.initialize_all()
        failed_init = [name for name, ok in init_results.items() if not ok]
        if failed_init:
            logger = get_logger("AURA")
            logger.warning(f"Modules failed to initialize: {', '.join(failed_init)}")
            self.lifecycle.degrade(f"init_failed:{','.join(failed_init)}")

        start_results = mm.start_all()
        failed_start = [name for name, ok in start_results.items() if not ok]
        if failed_start:
            logger = get_logger("AURA")
            logger.warning(f"Modules failed to start: {', '.join(failed_start)}")
            self.lifecycle.degrade(f"start_failed:{','.join(failed_start)}")

        logger = get_logger("AURA")
        logger.debug("Step 7/8: Modules initialized and started")
        self.event_bus.publish(SystemInitialized(source="modules"))

    def _step8_become_ready(self) -> None:
        if self.lifecycle.state == SystemState.DEGRADED:
            logger = get_logger("AURA")
            logger.warning("AURA entered RUNNING state in DEGRADED mode")
        else:
            self.lifecycle.start()
        self.event_bus.publish(SystemReady(source="AURA"))
        self.diagnostics.mark_boot_completed()
        logger = get_logger("AURA")
        duration = self.diagnostics.boot_duration_seconds
        if duration is not None:
            mc = self.module_manager.count() if self.module_manager else 0
            logger.info(
                f"Step 8/8: AURA READY in {duration:.3f}s "
                f"[state={self.lifecycle.state.value}, modules={mc}]"
            )
        else:
            logger.info(
                f"Step 8/8: AURA READY [state={self.lifecycle.state.value}, "
                f"modules={self.module_manager.count() if self.module_manager else 0}]"
            )

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def publish(self, event: Event) -> None:
        self.event_bus.publish(event)

    def subscribe(
        self,
        event_type: str | type[Event],
        handler: Any,
        filter_fn: Any = None,
    ) -> None:
        self.event_bus.subscribe(event_type, handler, filter_fn)

    @property
    def state(self) -> SystemState:
        return self.lifecycle.state

    @property
    def is_running(self) -> bool:
        return self.lifecycle.is_running

    def register_module(self, module_class: type[BaseModule]) -> BaseModule:
        if self.module_manager is None:
            raise RuntimeError("AURA not booted yet")
        return self.module_manager.register(module_class)

    def diagnostics_report(self) -> str:
        return self.diagnostics.formatted_report()

    def health_report(self) -> dict[str, Any]:
        if self.health_monitor is None:
            return {}
        result = self.health_monitor.perform_check()
        return {
            "overall": result.overall,
            "modules_total": result.modules_total,
            "modules_healthy": result.modules_healthy,
            "modules_degraded": result.modules_degraded,
            "modules_failed": result.modules_failed,
            "issues": result.issues,
            "last_check_at": result.last_check_at.isoformat() if result.last_check_at else None,
        }

    # ---------------------------------------------------------
    # Signal handling
    # ---------------------------------------------------------
    def _install_signal_handlers(self) -> None:
        if self._signal_handlers_installed:
            return
        if threading.current_thread() is not threading.main_thread():
            return
        try:
            def _handler(signum: int, frame: Any) -> None:
                self.request_shutdown(reason=f"signal_{signum}")

            signal.signal(signal.SIGINT, _handler)
            signal.signal(signal.SIGTERM, _handler)
            self._signal_handlers_installed = True
        except (ValueError, OSError, AttributeError):
            pass
