from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .models import Event

EventHandler = Callable[[Event], None]
EventFilter = Callable[[Event], bool]


@dataclass
class EventBus:
    _subscribers: dict[str, list[tuple[EventHandler, EventFilter | None]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _history: list[Event] = field(default_factory=list)
    _max_history: int = 1000
    _paused: bool = False
    _pending: list[Event] = field(default_factory=list)

    def subscribe(
        self,
        event_type: str | type[Event],
        handler: EventHandler,
        filter_fn: EventFilter | None = None,
    ) -> None:
        name = event_type if isinstance(event_type, str) else event_type.event_name()
        self._subscribers[name].append((handler, filter_fn))

    def unsubscribe(
        self,
        event_type: str | type[Event],
        handler: EventHandler,
    ) -> None:
        name = event_type if isinstance(event_type, str) else event_type.event_name()
        subs = self._subscribers.get(name, [])
        self._subscribers[name] = [(h, f) for h, f in subs if h is not handler]

    def publish(self, event: Event) -> None:
        if self._paused:
            self._pending.append(event)
            return

        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        name = event.event_name()
        subs: Iterable[tuple[EventHandler, EventFilter | None]] = list(
            self._subscribers.get(name, [])
        )
        for handler, filter_fn in subs:
            if filter_fn is None or filter_fn(event):
                try:
                    handler(event)
                except Exception:
                    from ..logging import get_logger

                    logger = get_logger("EventBus")
                    logger.exception(f"Handler failed for event {name}")

        global_subs = self._subscribers.get("*", [])
        for handler, filter_fn in global_subs:
            if filter_fn is None or filter_fn(event):
                try:
                    handler(event)
                except Exception:
                    from ..logging import get_logger

                    logger = get_logger("EventBus")
                    logger.exception(f"Global handler failed for event {name}")

    def publish_many(self, events: Iterable[Event]) -> None:
        for event in events:
            self.publish(event)

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False
        pending = list(self._pending)
        self._pending.clear()
        for event in pending:
            self.publish(event)

    def history(self, limit: int | None = None) -> list[Event]:
        if limit is None:
            return list(self._history)
        return list(self._history[-limit:])

    def clear_history(self) -> None:
        self._history.clear()

    def has_subscribers(self, event_type: str | type[Event] | None = None) -> bool:
        if event_type is None:
            return any(len(s) > 0 for s in self._subscribers.values())
        name = event_type if isinstance(event_type, str) else event_type.event_name()
        return len(self._subscribers.get(name, [])) > 0

    def subscriber_count(self, event_type: str | type[Event] | None = None) -> int:
        if event_type is None:
            return sum(len(s) for s in self._subscribers.values())
        name = event_type if isinstance(event_type, str) else event_type.event_name()
        return len(self._subscribers.get(name, []))
