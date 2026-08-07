from __future__ import annotations

from aura.container import DependencyContainer


class ServiceA:
    def __init__(self) -> None:
        self.value = "a"


class ServiceB:
    def __init__(self, a: ServiceA) -> None:
        self.a = a


class ServiceC:
    def __init__(self, b: ServiceB, extra: str = "default") -> None:
        self.b = b
        self.extra = extra


def test_register_instance_and_resolve():
    c = DependencyContainer()
    a = ServiceA()
    c.register(ServiceA, instance=a)
    assert c.resolve(ServiceA) is a


def test_register_class_with_factory_and_singleton():
    c = DependencyContainer()
    c.register(ServiceA, ServiceA, singleton=True)
    a1 = c.resolve(ServiceA)
    a2 = c.resolve(ServiceA)
    assert isinstance(a1, ServiceA)
    assert a1 is a2


def test_resolve_unknown_raises_key_error():
    c = DependencyContainer()
    try:
        c.resolve(ServiceA)
    except KeyError:
        return
    raise AssertionError("Expected KeyError")


def test_transient_not_singleton():
    c = DependencyContainer()
    c.register(ServiceA, ServiceA, singleton=False)
    a1 = c.resolve(ServiceA)
    a2 = c.resolve(ServiceA)
    assert a1 is not a2


def test_dependency_injection_via_type_hints():
    c = DependencyContainer()
    c.register(ServiceA, ServiceA)
    c.register(ServiceB, ServiceB)
    b = c.resolve(ServiceB)
    assert isinstance(b, ServiceB)
    assert isinstance(b.a, ServiceA)


def test_nested_dependency_injection():
    c = DependencyContainer()
    c.register(ServiceA, ServiceA)
    c.register(ServiceB, ServiceB)
    c.register(ServiceC, ServiceC)
    c_obj = c.resolve(ServiceC)
    assert isinstance(c_obj, ServiceC)
    assert c_obj.extra == "default"
    assert isinstance(c_obj.b, ServiceB)
    assert isinstance(c_obj.b.a, ServiceA)


def test_registered_interfaces_and_has():
    c = DependencyContainer()
    assert not c.has(ServiceA)
    c.register(ServiceA, ServiceA)
    assert c.has(ServiceA)
    assert ServiceA in c.registered_interfaces()


def test_named_services():
    c = DependencyContainer()
    c.register_named("hello", lambda: "world")
    c.register_named("num", lambda: 42, singleton=False)
    assert c.has_named("hello")
    assert c.resolve_named("hello") == "world"
    assert c.resolve_named("num") == 42
    assert set(c.registered_names()) == {"hello", "num"}


def test_clear_resets_state():
    c = DependencyContainer()
    c.register(ServiceA, ServiceA)
    c.resolve(ServiceA)
    assert c.has(ServiceA)
    c.clear()
    assert not c.has(ServiceA)
