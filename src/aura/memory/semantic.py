from __future__ import annotations

import threading
from typing import TYPE_CHECKING, ClassVar

from .models import Fact

if TYPE_CHECKING:
    from ..events import EventBus
    from .store import MemoryStore


class SemanticMemory:
    """Manages semantic long-term memory (abstract concepts, generalized facts)."""

    SINGLE_VALUED_PREDICATES: ClassVar[set[str]] = {
        "cumpleaños",
        "cumpleanos",
        "nombre",
        "color_favorito",
        "comida_favorita",
        "pelicula_favorita",
        "cancion_favorita",
        "deporte_favorito",
        "plato_favorito",
        "carrera",
        "moto",
        "email",
        "telefono",
        "edad",
        "actividad",
        "ciudad",
        "pais",
        "país",
        "fecha_de_nacimiento",
    }

    def __init__(
        self,
        event_bus: EventBus | None = None,
        store: MemoryStore | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.store = store
        self._facts: list[Fact] = []
        self._lock = threading.RLock()
        if self.store is not None:
            self.load_from_store()

    @classmethod
    def is_single_valued(cls, predicate: str) -> bool:
        pred_clean = predicate.lower().strip()
        return (
            pred_clean in cls.SINGLE_VALUED_PREDICATES
            or pred_clean.endswith(("_favorito", "_favorita"))
        )

    def load_from_store(self) -> None:
        with self._lock:
            if self.store is not None:
                persisted = self.store.get_facts()
                existing_ids = {f.id for f in self._facts}
                for fact in persisted:
                    if fact.id not in existing_ids:
                        self._facts.append(fact)
                from ..logging import get_logger

                logger = get_logger("SemanticMemory")
                logger.info(f"Loaded {len(self._facts)} facts from memory store.")

    def add_fact(self, fact: Fact) -> Fact:
        with self._lock:
            subj_clean = fact.subject.lower().strip()
            pred_clean = fact.predicate.lower().strip()
            obj_clean = fact.object_val.lower().strip()

            if self.is_single_valued(fact.predicate):
                # Remove obsolete facts for the same subject & single-valued predicate
                obsolete = [
                    f
                    for f in self._facts
                    if f.subject.lower().strip() == subj_clean
                    and f.predicate.lower().strip() == pred_clean
                ]
                for old_f in obsolete:
                    if old_f in self._facts:
                        self._facts.remove(old_f)
                    if self.store is not None:
                        self.store.delete_fact(old_f.id)

            # Idempotency check: if identical fact (subject, predicate, object_val) exists:
            existing_identical = [
                f
                for f in self._facts
                if f.subject.lower().strip() == subj_clean
                and f.predicate.lower().strip() == pred_clean
                and f.object_val.lower().strip() == obj_clean
            ]
            if existing_identical:
                return existing_identical[0]

            self._facts.append(fact)
            if self.store is not None:
                self.store.save_fact(fact)

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
            if self.store is not None:
                store_results = self.store.get_facts(subject=subject, predicate=predicate)
                if store_results:
                    return store_results

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
            if self.store is not None:
                store_results = self.store.get_facts()
                if store_results:
                    return store_results
            return list(self._facts)

    def count(self) -> int:
        with self._lock:
            return len(self.all_facts())
