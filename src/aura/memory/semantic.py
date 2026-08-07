from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from .models import Fact

if TYPE_CHECKING:
    from ..events import EventBus


class SemanticMemory:
    """Manages semantic long-term memory (abstract concepts, generalized facts)."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self._facts: list[Fact] = []
        self._lock = threading.RLock()

    def add_fact(self, fact: Fact) -> Fact:
        with self._lock:
            self._facts.append(fact)

            if self.event_bus is not None:
                from ..events import FactLearned

                self.event_bus.publish(
                    FactLearned(
                        source="SemanticMemory",
                        fact_id=fact.id,
                        subject=fact.subject,
                        predicate=fact.predicate,
                        object_val=fact.object_val,
                    )
                )
            return fact

    def query_facts(self, subject: str | None = None, predicate: str | None = None) -> list[Fact]:
        with self._lock:
            results = list(self._facts)
            if subject is not None:
                subj_lower = subject.lower()
                results = [f for f in results if subj_lower in f.subject.lower()]
            if predicate is not None:
                pred_lower = predicate.lower()
                results = [f for f in results if pred_lower in f.predicate.lower()]
            return results

    def all_facts(self) -> list[Fact]:
        with self._lock:
            return list(self._facts)

    def count(self) -> int:
        with self._lock:
            return len(self._facts)
