from __future__ import annotations

import threading
import time

from aura.events import Event, EventBus


class CustomTestEvent(Event):
    pass


def test_event_bus_concurrent_publish_and_subscribe():
    bus = EventBus()
    received: list[int] = []

    def handler(e: Event) -> None:
        if isinstance(e, CustomTestEvent):
            cnt = e.payload.get("count")
            if isinstance(cnt, int):
                received.append(cnt)

    bus.subscribe(CustomTestEvent, handler)

    def worker(start_idx: int) -> None:
        for i in range(50):
            bus.publish(CustomTestEvent(payload={"count": start_idx + i}))
            time.sleep(0.001)

    threads = [threading.Thread(target=worker, args=(100 * t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(received) == 250
    assert bus.history()
