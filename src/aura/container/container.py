from __future__ import annotations

import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass
class ServiceDescriptor:
    interface: type
    factory: Callable[[], Any]
    singleton: bool = True
    _instance: Any = None


@dataclass
class DependencyContainer:
    _services: dict[type, ServiceDescriptor] = field(default_factory=dict)
    _named: dict[str, ServiceDescriptor] = field(default_factory=dict)
    _instances: dict[type, Any] = field(default_factory=dict)
    _building: set[type] = field(default_factory=set)

    def register(
        self,
        interface: type,
        implementation: type[Any] | Callable[[], Any] | None = None,
        *,
        singleton: bool = True,
        instance: Any | None = None,
    ) -> None:
        if instance is not None:
            self._instances[interface] = instance
            factory: Callable[[], Any] = lambda: instance
            self._services[interface] = ServiceDescriptor(
                interface=interface, factory=factory, singleton=True, _instance=instance
            )
            return

        if implementation is None:

            def _impl_factory(iface: type[Any] = interface) -> Any:
                return self._build_instance(iface)

            impl: Callable[[], Any] = _impl_factory
        elif isinstance(implementation, type):

            def _cls_factory(cls: type[Any] = implementation) -> Any:
                return self._build_instance(cls)

            impl = _cls_factory
        else:
            impl = implementation

        self._services[interface] = ServiceDescriptor(
            interface=interface, factory=impl, singleton=singleton
        )

    def register_named(
        self,
        name: str,
        factory: Callable[[], Any] | type[Any],
        *,
        singleton: bool = True,
    ) -> None:
        if isinstance(factory, type):

            def _named_factory(cls: type[Any] = factory) -> Any:
                return self._build_instance(cls)

            fac: Callable[[], Any] = _named_factory
        else:
            fac = factory
        self._named[name] = ServiceDescriptor(
            interface=type(None), factory=fac, singleton=singleton
        )

    def resolve(self, interface: type[T]) -> T:
        if interface in self._instances:
            return typing.cast(T, self._instances[interface])

        descriptor = self._services.get(interface)
        if descriptor is None:
            raise KeyError(f"Service not registered: {interface.__name__}")

        if not descriptor.singleton:
            return typing.cast(T, descriptor.factory())

        if interface in self._building:
            raise RecursionError(
                f"Circular dependency detected while building {interface.__name__}"
            )

        self._building.add(interface)
        try:
            instance = descriptor.factory()
        finally:
            self._building.discard(interface)

        self._instances[interface] = instance
        descriptor._instance = instance
        return typing.cast(T, instance)

    def resolve_named(self, name: str) -> Any:
        descriptor = self._named.get(name)
        if descriptor is None:
            raise KeyError(f"Named service not registered: {name}")
        if descriptor.singleton:
            if descriptor._instance is None:
                descriptor._instance = descriptor.factory()
            return descriptor._instance
        return descriptor.factory()

    def has(self, interface: type) -> bool:
        return interface in self._services or interface in self._instances

    def has_named(self, name: str) -> bool:
        return name in self._named

    def registered_interfaces(self) -> list[type]:
        return sorted(self._services.keys(), key=lambda c: c.__name__)

    def registered_names(self) -> list[str]:
        return sorted(self._named.keys())

    def clear(self) -> None:
        self._services.clear()
        self._named.clear()
        self._instances.clear()
        self._building.clear()

    def _build_instance(self, cls: type[Any]) -> Any:
        import inspect

        try:
            hints = typing.get_type_hints(cls.__init__)
        except Exception:
            hints = {}

        try:
            sig = inspect.signature(cls.__init__)
        except (TypeError, ValueError):
            return cls()

        kwargs: dict[str, Any] = {}
        for name, param in list(sig.parameters.items())[1:]:
            annotation = hints.get(name, param.annotation)
            if annotation is inspect.Parameter.empty:
                if param.default is not inspect.Parameter.empty:
                    kwargs[name] = param.default
                continue
            if isinstance(annotation, type) and self.has(annotation):
                try:
                    kwargs[name] = self.resolve(annotation)
                except Exception:
                    if param.default is not inspect.Parameter.empty:
                        kwargs[name] = param.default
                    else:
                        raise
            elif annotation in self._services or annotation in self._instances:
                try:
                    kwargs[name] = self.resolve(annotation)
                except Exception:
                    if param.default is not inspect.Parameter.empty:
                        kwargs[name] = param.default
                    else:
                        raise
            elif param.default is not inspect.Parameter.empty:
                kwargs[name] = param.default
        return cls(**kwargs)
