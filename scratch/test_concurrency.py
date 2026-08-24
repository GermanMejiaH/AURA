from __future__ import annotations

import os
import shutil
import threading
import time
from typing import Any

from aura.events import Event, EventBus
from aura.memory import MemoryModule
from aura.memory.models import Fact, Preference
from aura.memory.store import SQLiteMemoryStore


def test_concurrency() -> dict[str, Any]:
    print("=== STAGE 26.4 AUDIT 1: CONCURRENT ACCESS SAFETY ===")
    db_path = "scratch/test_concurrency.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    store = SQLiteMemoryStore(db_path=db_path)
    mem_mod = MemoryModule(store=store)
    event_bus = EventBus()

    errors: list[str] = []
    writes_count = 0
    reads_count = 0
    lock = threading.Lock()

    def worker_writer(thread_id: int) -> None:
        nonlocal writes_count
        for i in range(50):
            try:
                fact = Fact(subject="usuario", predicate=f"key_{thread_id}_{i}", object_val=f"val_{i}")
                mem_mod.semantic.add_fact(fact)
                mem_mod.preferences.set_preference(f"pref_{thread_id}_{i}", f"val_{i}")
                event_bus.publish(Event(source="test_worker"))
                with lock:
                    writes_count += 2
            except Exception as e:
                with lock:
                    errors.append(f"Thread {thread_id} write error: {e}")

    def worker_reader(thread_id: int) -> None:
        nonlocal reads_count
        for i in range(50):
            try:
                _ = mem_mod.retrieval.query(f"key_{thread_id}_{i}")
                with lock:
                    reads_count += 1
            except Exception as e:
                with lock:
                    errors.append(f"Thread {thread_id} read error: {e}")

    threads: list[threading.Thread] = []
    start_t = time.perf_counter()

    for t_id in range(5):
        t_w = threading.Thread(target=worker_writer, args=(t_id,))
        t_r = threading.Thread(target=worker_reader, args=(t_id,))
        threads.extend([t_w, t_r])
        t_w.start()
        t_r.start()

    for t in threads:
        t.join(timeout=10.0)

    duration = time.perf_counter() - start_t
    store.close()

    if os.path.exists(db_path):
        os.remove(db_path)

    passed = (len(errors) == 0 and writes_count == 500 and reads_count == 250)
    print(f"Concurrent Writes: {writes_count} | Reads: {reads_count} | Errors: {len(errors)} | Duration: {duration:.2f}s | Passed: {passed}")
    return {
        "writes_count": writes_count,
        "reads_count": reads_count,
        "errors": errors,
        "duration_sec": duration,
        "passed": passed,
    }


if __name__ == "__main__":
    test_concurrency()
