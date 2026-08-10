from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from .episodic import EpisodicMemory
from .models import Fact, MemoryQueryResult, Preference
from .preferences import UserPreferencesMemory
from .semantic import SemanticMemory

if TYPE_CHECKING:
    from ..events import EventBus


def normalize_text(text: str) -> str:
    """Removes Spanish accents, converts to lowercase, and strips non-alphanumeric characters."""
    nfd = unicodedata.normalize("NFD", text.lower())
    without_accents = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s]", " ", without_accents).strip()


# Extensible concept/alias dictionary mapping canonical concepts to normalized variant tokens
CONCEPT_ALIASES: dict[str, set[str]] = {
    "cumpleaños": {
        "cumpleanos",
        "cumpleano",
        "cumple",
        "cumpli",
        "cumplo",
        "cumplir",
        "cumplire",
        "nacimiento",
        "naci",
        "aniversario",
        "edad",
    },
    "color_favorito": {
        "color",
        "favorito",
        "preferido",
        "gusta",
        "prefiero",
    },
    "actividad": {
        "estudiando",
        "estudio",
        "estudiar",
        "trabajo",
        "trabajando",
        "haciendo",
        "dedico",
        "carrera",
    },
    "moto": {
        "moto",
        "motocicleta",
        "vehiculo",
        "transporte",
    },
    "nombre": {
        "nombre",
        "llamo",
        "llamaron",
    },
}


class MemoryRetrievalEngine:
    """Layered semantic retrieval & scoring engine across Episodic, Semantic, and Preferences.

    Scoring Weights:
    - W_EXACT_PREDICATE = 1.0 (exact match between query tokens and predicate)
    - W_CONCEPT_ALIAS   = 0.8 (concept alias match between query tokens and predicate concept)
    - W_TOKEN_OVERLAP   = 0.5 (token overlap between query and object value/details)
    - W_SUBJECT_MATCH   = 0.3 (subject match)
    """

    W_EXACT_PREDICATE = 1.0
    W_CONCEPT_ALIAS = 0.8
    W_TOKEN_OVERLAP = 0.5
    W_SUBJECT_MATCH = 0.3

    def __init__(
        self,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        preferences: UserPreferencesMemory,
        event_bus: EventBus | None = None,
    ) -> None:
        self.episodic = episodic
        self.semantic = semantic
        self.preferences = preferences
        self.event_bus = event_bus

    def _get_query_tokens(self, search_text: str) -> set[str]:
        norm = normalize_text(search_text)
        return {w for w in norm.split() if len(w) >= 2}

    def score_fact(self, fact: Fact, query_tokens: set[str]) -> float:
        norm_pred = normalize_text(fact.predicate)
        norm_obj = normalize_text(fact.object_val)
        norm_subj = normalize_text(fact.subject)
        obj_tokens = set(norm_obj.split())

        score = 0.0

        # 1. Exact predicate match
        if norm_pred in query_tokens or norm_pred.replace("_", " ") in normalize_text(
            " ".join(query_tokens)
        ):
            score += self.W_EXACT_PREDICATE

        # 2. Concept alias match
        canonical_concept = norm_pred.replace("_", " ")
        aliases = CONCEPT_ALIASES.get(fact.predicate, set()) | CONCEPT_ALIASES.get(
            canonical_concept, set()
        )
        if any(token in aliases for token in query_tokens):
            score += self.W_CONCEPT_ALIAS

        # 3. Token overlap with object value
        overlap = query_tokens.intersection(obj_tokens)
        if overlap:
            score += self.W_TOKEN_OVERLAP * (len(overlap) / max(len(query_tokens), 1))

        # 4. Subject match
        if norm_subj in query_tokens or "usuario" in norm_subj:
            score += self.W_SUBJECT_MATCH

        # Multiplier by fact confidence
        return score * float(fact.confidence)

    def score_preference(self, pref: Preference, query_tokens: set[str]) -> float:
        norm_key = normalize_text(pref.key)
        norm_val = normalize_text(pref.value)
        val_tokens = set(norm_val.split())

        score = 0.0
        if norm_key in query_tokens:
            score += self.W_EXACT_PREDICATE

        aliases = CONCEPT_ALIASES.get(pref.key, set())
        if any(token in aliases for token in query_tokens):
            score += self.W_CONCEPT_ALIAS

        overlap = query_tokens.intersection(val_tokens)
        if overlap:
            score += self.W_TOKEN_OVERLAP * (len(overlap) / max(len(query_tokens), 1))

        return score

    def query(self, search_text: str, limit: int = 5) -> MemoryQueryResult:
        query_tokens = self._get_query_tokens(search_text)

        # 1. Search Semantic Facts
        all_facts = self.semantic.all_facts()
        fact_scores: list[tuple[float, Fact]] = []
        for f in all_facts:
            s = self.score_fact(f, query_tokens)
            if s > 0.1 or len(all_facts) <= 3:
                fact_scores.append((s, f))

        fact_scores.sort(key=lambda x: x[0], reverse=True)
        matched_facts = [f for _, f in fact_scores[:limit]]

        # 2. Search User Preferences
        all_prefs = self.preferences.all_preferences()
        pref_scores: list[tuple[float, Preference]] = []
        for p in all_prefs:
            s = self.score_preference(p, query_tokens)
            if s > 0.1 or len(all_prefs) <= 3:
                pref_scores.append((s, p))

        pref_scores.sort(key=lambda x: x[0], reverse=True)
        matched_prefs = [p for _, p in pref_scores[:limit]]

        # 3. Search Episodic Memory
        episodes = self.episodic.search_episodes(search_text, limit=limit)

        result = MemoryQueryResult(
            episodes=episodes[:limit],
            facts=matched_facts[:limit],
            preferences=matched_prefs[:limit],
        )

        if self.event_bus is not None:
            from ..events import MemoryQueried

            total = len(episodes) + len(matched_facts) + len(matched_prefs)
            self.event_bus.publish(
                MemoryQueried(
                    source="MemoryRetrievalEngine",
                    query=search_text,
                    results_count=total,
                )
            )

        return result
