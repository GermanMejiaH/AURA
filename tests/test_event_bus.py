from __future__ import annotations

from aura.events import (
    ErrorOccurred,
    Event,
    EventBus,
    SystemBooting,
    SystemReady,
)


def test_event_name_defaults_to_class_name():
    class SomethingHappened(Event):
        pass

    assert SomethingHappened.event_name() == "SomethingHappened"


def test_event_name_can_be_overridden():
    class MyEvent(Event):
        __event_name__ = "CustomName"

    assert MyEvent.event_name() == "CustomName"


def test_event_is_immutable_via_payload_id():
    e1 = SystemReady()
    e2 = SystemReady()
    assert e1.event_id != e2.event_id


def test_event_to_dict_contains_event_type():
    e = SystemReady(source="test")
    data = e.to_dict()
    assert data["event_type"] == "SystemReady"
    assert data["source"] == "test"
    assert "event_id" in data
    assert "timestamp" in data


def test_event_bus_publish_and_subscribe():
    bus = EventBus()
    received: list[Event] = []

    def handler(e: Event) -> None:
        received.append(e)

    bus.subscribe(SystemReady, handler)
    event = SystemReady(source="unit-test")
    bus.publish(event)

    assert len(received) == 1
    assert received[0] is event


def test_event_bus_multiple_subscribers():
    bus = EventBus()
    r1: list[Event] = []
    r2: list[Event] = []

    bus.subscribe(SystemReady, lambda e: r1.append(e))
    bus.subscribe(SystemReady, lambda e: r2.append(e))

    bus.publish(SystemReady())
    assert len(r1) == 1
    assert len(r2) == 1


def test_event_bus_unsubscribe():
    bus = EventBus()
    received: list[Event] = []

    def h(e: Event) -> None:
        received.append(e)

    bus.subscribe(SystemReady, h)
    bus.unsubscribe(SystemReady, h)
    bus.publish(SystemReady())
    assert received == []


def test_event_bus_history_is_recorded():
    bus = EventBus()
    bus.publish(SystemBooting())
    bus.publish(SystemReady())
    history = bus.history()
    assert len(history) == 2
    assert isinstance(history[0], SystemBooting)
    assert isinstance(history[1], SystemReady)


def test_event_bus_filter_works():
    bus = EventBus()
    received: list[Event] = []

    def handler(e: Event) -> None:
        received.append(e)

    def only_from_foo(e: Event) -> bool:
        return e.source == "foo"

    bus.subscribe(SystemReady, handler, filter_fn=only_from_foo)
    bus.publish(SystemReady(source="bar"))
    bus.publish(SystemReady(source="foo"))
    assert len(received) == 1
    assert received[0].source == "foo"


def test_event_bus_subscriber_count_and_has_subscribers():
    bus = EventBus()
    assert not bus.has_subscribers()
    assert bus.subscriber_count() == 0

    bus.subscribe(SystemReady, lambda e: None)
    assert bus.has_subscribers(SystemReady)
    assert bus.subscriber_count(SystemReady) == 1
    assert bus.subscriber_count() == 1


def test_event_bus_pause_and_resume():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(SystemReady, lambda e: received.append(e))

    bus.pause()
    bus.publish(SystemReady(source="a"))
    bus.publish(SystemReady(source="b"))
    assert len(received) == 0

    bus.resume()
    assert len(received) == 2


def test_event_bus_global_wildcard_subscription():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("*", lambda e: received.append(e))
    bus.publish(SystemBooting())
    bus.publish(SystemReady())
    bus.publish(ErrorOccurred())
    assert len(received) == 3
