from __future__ import annotations

import importlib
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..config import ConfigurationManager
from ..container import DependencyContainer
from ..events import EventBus, ModuleLoaded, ModuleStarted, ModuleStopped
from ..logging import get_logger
from ..modules.base import BaseModule, ModuleHealth, ModuleStatus
from .lifecycle import LifecycleManager

ModuleClass = type[BaseModule]


@dataclass
class ModuleManager:
    config: ConfigurationManager
    container: DependencyContainer
    event_bus: EventBus
    lifecycle: LifecycleManager

    _modules: dict[str, BaseModule] = field(default_factory=dict)
    _order: list[str] = field(default_factory=list)

    def register(
        self,
        module_class: ModuleClass,
        *,
        auto_init: bool = False,
    ) -> BaseModule:
        name = module_class.name if module_class.name != "base-module" else module_class.__name__

        if name in self._modules:
            return self._modules[name]

        logger = get_logger("ModuleManager")
        logger.debug(f"Registering module: {name}")

        try:
            instance = self.container.resolve(module_class)
        except Exception:
            try:
                instance = module_class(
                    config=self.config,
                    container=self.container,
                    event_bus=self.event_bus,
                )
            except Exception as exc:
                logger.error(f"Failed to instantiate module {name}: {exc}")
                raise

        self._modules[name] = instance
        self._order.append(name)
        self.container.register(module_class, instance=instance)

        try:
            instance.load()
        except Exception as exc:
            logger.error(f"Failed to load module {name}: {exc}")
            instance.set_status(ModuleStatus.ERROR, str(exc))
        else:
            self.event_bus.publish(ModuleLoaded(source="ModuleManager", module_name=name))

        if auto_init:
            self._initialize_module(name, instance)

        return instance

    def register_many(self, module_classes: Iterable[ModuleClass]) -> list[BaseModule]:
        ordered = sorted(module_classes, key=lambda c: getattr(c, "priority", 100))
        return [self.register(cls) for cls in ordered]

    def initialize_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        logger = get_logger("ModuleManager")
        for name in self._order:
            module = self._modules[name]
            results[name] = self._initialize_module(name, module)
        success_count = sum(1 for ok in results.values() if ok)
        logger.info(f"Initialized {success_count}/{len(results)} modules")
        return results

    def start_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        logger = get_logger("ModuleManager")
        for name in self._order:
            module = self._modules[name]
            ok = self._start_module(name, module)
            results[name] = ok
        started = sum(1 for ok in results.values() if ok)
        logger.info(f"Started {started}/{len(results)} modules")
        return results

    def stop_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        logger = get_logger("ModuleManager")
        for name in reversed(self._order):
            module = self._modules.get(name)
            if module is None:
                continue
            ok = self._stop_module(name, module)
            results[name] = ok
        stopped = sum(1 for ok in results.values() if ok)
        logger.info(f"Stopped {stopped}/{len(results)} modules")
        return results

    def pause_all(self) -> None:
        for name in self._order:
            module = self._modules[name]
            if module.health.status == ModuleStatus.RUNNING:
                try:
                    module.pause()
                except Exception:
                    logger = get_logger("ModuleManager")
                    logger.exception(f"Failed to pause module {name}")

    def resume_all(self) -> None:
        for name in self._order:
            module = self._modules[name]
            if module.health.status == ModuleStatus.PAUSED:
                try:
                    module.resume()
                except Exception:
                    logger = get_logger("ModuleManager")
                    logger.exception(f"Failed to resume module {name}")

    def has(self, name: str) -> bool:
        return name in self._modules

    def get(self, name: str) -> BaseModule | None:
        return self._modules.get(name)

    def list_modules(self) -> list[tuple[str, BaseModule]]:
        return [(n, self._modules[n]) for n in self._order if n in self._modules]

    def count(self) -> int:
        return len(self._modules)

    def health_snapshot(self) -> dict[str, ModuleHealth]:
        return {name: module.health for name, module in self._modules.items()}

    def discover(self, search_paths: Iterable[str] | None = None) -> list[str]:
        paths = list(search_paths or self.config.get("modules.search_paths", []) or [])
        found: list[str] = []
        logger = get_logger("ModuleManager")
        for path in paths:
            try:
                pkg = importlib.import_module(path)
            except Exception as exc:
                logger.debug(f"Could not load module path {path}: {exc}")
                continue
            if not hasattr(pkg, "__AURA_MODULES__"):
                continue
            modules_declared = getattr(pkg, "__AURA_MODULES__", []) or []
            for mod_cls in modules_declared:
                if isinstance(mod_cls, type) and issubclass(mod_cls, BaseModule):
                    self.register(mod_cls)
                    found.append(mod_cls.__name__)
        if found:
            logger.info(f"Discovered {len(found)} modules: {', '.join(found)}")
        return found

    def _initialize_module(self, name: str, module: BaseModule) -> bool:
        logger = get_logger("ModuleManager")
        if module.health.status in {ModuleStatus.READY, ModuleStatus.RUNNING}:
            return True
        try:
            module.initialize()
        except Exception as exc:
            logger.error(f"Failed to initialize module {name}: {exc}")
            if module.required:
                self.lifecycle.degrade(f"required_module_failed:{name}")
            return False
        return True

    def _start_module(self, name: str, module: BaseModule) -> bool:
        logger = get_logger("ModuleManager")
        if module.health.status == ModuleStatus.RUNNING:
            return True
        allowed = {ModuleStatus.READY, ModuleStatus.PAUSED, ModuleStatus.DEGRADED}
        if module.health.status not in allowed:
            logger.warning(f"Cannot start module {name}, status is {module.health.status.value}")
            return False
        try:
            module.start()
            self.event_bus.publish(ModuleStarted(source="ModuleManager", module_name=name))
        except Exception as exc:
            logger.error(f"Failed to start module {name}: {exc}")
            module.set_status(ModuleStatus.ERROR, str(exc))
            if module.required:
                self.lifecycle.degrade(f"required_module_start_failed:{name}")
            return False
        return True

    def _stop_module(self, name: str, module: BaseModule) -> bool:
        logger = get_logger("ModuleManager")
        if module.health.status in {ModuleStatus.STOPPED, ModuleStatus.UNLOADED}:
            return True
        try:
            module.shutdown()
            self.event_bus.publish(ModuleStopped(source="ModuleManager", module_name=name))
        except Exception as exc:
            logger.exception(f"Failed to stop module {name}: {exc}")
            module.set_status(ModuleStatus.ERROR, str(exc))
            return False
        return True
