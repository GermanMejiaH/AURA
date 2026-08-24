from __future__ import annotations

import gc
import threading
import time
import tracemalloc
from typing import Any

from aura.cognition.context import CognitiveContextBuilder
from aura.container import DependencyContainer
from aura.events import Event, EventBus
from aura.memory import MemoryModule
from aura.memory.models import Fact
from aura.memory.store import SQLiteMemoryStore


def test_endurance(num_cycles: int = 500) -> dict[str, Any]:
    print(f"=== STAGE 26.4 AUDIT 6: LONG-RUN ENDURANCE AUDIT ({num_cycles} CYCLES) ===")
    tracemalloc.start()

    store = SQLiteMemoryStore(db_path=":memory:")
    mem_mod = MemoryModule(store=store)
    event_bus = EventBus()

    container = DependencyContainer()
    container.register(MemoryModule, instance=mem_mod)
    container.register(EventBus, instance=event_bus)

    context_builder = CognitiveContextBuilder(container=container)

    initial_threads = threading.active_count()
    mem_snapshots: list[int] = []

    start_time = time.perf_counter()

    for i in range(num_cycles):
        # 1. Store memory
        fact = Fact(subject="usuario", predicate=f"key_{i}", object_val=f"val_{i}")
        mem_mod.semantic.add_fact(fact)

        # 2. Query memory
        _ = mem_mod.retrieval.query(f"key_{i}")

        # 3. Build context
        ctx = context_builder.build(input_text=f"Turn {i} question")
        _ = ctx.to_system_prompt()
        _ = ctx.to_formatted_prompt()

        # 4. Event publication
        event_bus.publish(Event(source="EnduranceTest"))

        if i % 100 == 0:
            current_mem, peak_mem = tracemalloc.get_traced_memory()
            mem_snapshots.append(current_mem)

    gc.collect()
    final_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    final_threads = threading.active_count()
    duration = time.perf_counter() - start_time

    # Memory growth rate evaluation
    first_mem = mem_snapshots[0] if mem_snapshots else 1
    mem_growth_mb = (final_mem - first_mem) / (1024 * 1024)

    thread_leak = (final_threads > initial_threads)
    excessive_memory_leak = (mem_growth_mb > 15.0)

    passed = (not thread_leak and not excessive_memory_leak)
    print(
        f"Completed {num_cycles} Cycles in {duration:.2f}s | "
        f"Initial Threads: {initial_threads} -> Final: {final_threads} | "
        f"Memory Growth: {mem_growth_mb:.2f} MB | Passed: {passed}"
    )

    store.close()

    return {
        "num_cycles": num_cycles,
        "duration_sec": duration,
        "initial_threads": initial_threads,
        "final_threads": final_threads,
        "peak_mem_bytes": peak_mem,
        "mem_growth_mb": mem_growth_mb,
        "thread_leak": thread_leak,
        "passed": passed,
    }


if __name__ == "__main__":
    test_endurance()
