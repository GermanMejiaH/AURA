from __future__ import annotations

import json
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from .models import Episode, Fact, MemoryQueryResult, Preference
from .store import SQLiteMemoryStore

if TYPE_CHECKING:
    from ..events import EventBus
    from .episodic import EpisodicMemory
    from .preferences import UserPreferencesMemory
    from .semantic import SemanticMemory


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
    "comida_favorita": {
        "comida",
        "favorita",
        "preferida",
        "gusta",
        "prefiero",
        "plato",
        "alimento",
        "comer",
        "ahorita",
        "menu",
    },
    "actividad": {
        "estudiando",
        "estudio",
        "estudiar",
        "estudie",
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
    "edad": {
        "edad",
        "anos",
        "anios",
        "cumpleanos",
        "cumple",
        "tengo",
    },
    "ciudad": {
        "ciudad",
        "vivo",
        "resido",
        "vivir",
        "residir",
        "donde",
        "ubicacion",
    },
    "ocupacion": {
        "ocupacion",
        "trabajo",
        "desarrollador",
        "profesion",
        "empleo",
        "oficio",
    },
    "empleador": {
        "empleador",
        "empresa",
        "compañia",
        "compania",
        "trabajo",
    },
    "carrera": {
        "carrera",
        "estudio",
        "estudiar",
        "estudiando",
        "profesion",
    },
    "proyecto": {
        "proyecto",
        "proyectos",
        "sistema",
        "desarrollo",
    },
    "habilidad": {
        "habilidad",
        "habilidades",
        "programacion",
        "conocimiento",
    },
}

STOPWORDS = {
    "a",
    "al",
    "an",
    "and",
    "ante",
    "at",
    "by",
    "como",
    "con",
    "contra",
    "de",
    "del",
    "desde",
    "el",
    "en",
    "entre",
    "es",
    "for",
    "fue",
    "hacer",
    "hacerlo",
    "in",
    "la",
    "las",
    "los",
    "no",
    "o",
    "of",
    "on",
    "or",
    "para",
    "por",
    "que",
    "se",
    "según",
    "ser",
    "si",
    "sin",
    "sobre",
    "son",
    "the",
    "to",
    "tras",
    "un",
    "una",
    "unos",
    "unas",
    "with",
    "y",
}

# Deterministic scoring weight constants for MemoryRetriever
W_KEYWORD = 0.40
W_INTENT = 0.25
W_TOOL = 0.20
W_OUTCOME = 0.10
W_RECENCY = 0.05


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

    OPEN_RECALL_PATTERNS: ClassVar[tuple[str, ...]] = (
        r"\brecuerdas\b",
        r"\bsabes(?:\s+(?:de|sobre))?\b",
        r"\bqui[eé]n\s+soy\b",
        r"\bh[aá]blame\s+de\s+m[ií]\b",
        r"\bqu[eé]\s+conoces\b",
        r"\bdatos\b",
        r"\binformaci[oó]n\b",
    )

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

    @classmethod
    def _is_open_recall_query(cls, search_text: str, query_tokens: set[str]) -> bool:
        norm = normalize_text(search_text)
        return any(re.search(pat, norm, re.IGNORECASE) for pat in cls.OPEN_RECALL_PATTERNS)

    def score_fact(self, fact: Fact, query_tokens: set[str], is_open_recall: bool = False) -> float:
        norm_pred = normalize_text(fact.predicate)
        norm_obj = normalize_text(fact.object_val)
        norm_subj = normalize_text(fact.subject)
        obj_tokens = set(norm_obj.split())

        score = 0.0

        if norm_pred in query_tokens or norm_pred.replace("_", " ") in normalize_text(
            " ".join(query_tokens)
        ):
            score += self.W_EXACT_PREDICATE

        canonical_concept = norm_pred.replace("_", " ")
        pred_base = norm_pred.split("_")[0]
        aliases = (
            CONCEPT_ALIASES.get(fact.predicate, set())
            | CONCEPT_ALIASES.get(canonical_concept, set())
            | CONCEPT_ALIASES.get(pred_base, set())
        )
        if any(token in aliases for token in query_tokens):
            score += self.W_CONCEPT_ALIAS

        overlap = query_tokens.intersection(obj_tokens)
        if overlap:
            score += self.W_TOKEN_OVERLAP * (len(overlap) / max(len(query_tokens), 1))

        # Unconditional evaluation of subject match (independent of predicate match)
        personal_tokens = {"yo", "soy", "mi", "mis", "mio", "mía", "mia", "usuario"}
        if (
            norm_subj in query_tokens
            or query_tokens.intersection(personal_tokens)
            or is_open_recall
        ):
            score += self.W_SUBJECT_MATCH

        return score * fact.confidence

    def score_preference(
        self, pref: Preference, query_tokens: set[str], is_open_recall: bool = False
    ) -> float:
        from .canonicalization import canonicalize_key

        canon_k = canonicalize_key(pref.key)
        norm_key = normalize_text(canon_k)
        norm_val = normalize_text(pref.value)
        val_tokens = set(norm_val.split())

        score = 0.0
        norm_phrase = normalize_text(" ".join(query_tokens))
        if norm_key in query_tokens or norm_key.replace("_", " ") in norm_phrase:
            score += self.W_EXACT_PREDICATE

        aliases = CONCEPT_ALIASES.get(canon_k, set()) | CONCEPT_ALIASES.get(pref.key, set())
        if any(token in aliases for token in query_tokens):
            score += self.W_CONCEPT_ALIAS

        overlap = query_tokens.intersection(val_tokens)
        if overlap:
            score += self.W_TOKEN_OVERLAP * (len(overlap) / max(len(query_tokens), 1))

        # Unconditional evaluation of personal/user match for preferences
        personal_tokens = {"yo", "soy", "mi", "mis", "mio", "mía", "mia", "usuario"}
        if query_tokens.intersection(personal_tokens) or is_open_recall:
            score += self.W_SUBJECT_MATCH

        return score

    def query(self, search_text: str, limit: int = 5) -> MemoryQueryResult:
        query_tokens = self._get_query_tokens(search_text)
        is_open = self._is_open_recall_query(search_text, query_tokens)

        all_facts = self.semantic.all_facts()
        fact_scores: list[tuple[float, Fact]] = []
        for f in all_facts:
            s = self.score_fact(f, query_tokens, is_open_recall=is_open)
            if s > 0.1:
                fact_scores.append((s, f))

        fact_scores.sort(
            key=lambda x: (x[0], x[1].created_at if hasattr(x[1], "created_at") else 0),
            reverse=True,
        )

        # If a strong predicate/concept match exists, suppress generic subject-only noise
        max_fact_score = fact_scores[0][0] if fact_scores else 0.0
        if max_fact_score >= self.W_CONCEPT_ALIAS and not is_open:
            fact_scores = [item for item in fact_scores if item[0] > (self.W_SUBJECT_MATCH + 0.05)]

        matched_facts = [f for _, f in fact_scores[:limit]]

        all_prefs = self.preferences.all_preferences()
        pref_scores: list[tuple[float, Preference]] = []
        for p in all_prefs:
            s = self.score_preference(p, query_tokens, is_open_recall=is_open)
            if s > 0.1:
                # If not an open recall query, require key or concept alias match for preferences
                from .canonicalization import canonicalize_key

                canon_k = canonicalize_key(p.key)
                norm_k = normalize_text(canon_k)
                aliases = CONCEPT_ALIASES.get(canon_k, set()) | CONCEPT_ALIASES.get(p.key, set())
                has_key_match = norm_k in query_tokens or any(t in aliases for t in query_tokens)

                if is_open or has_key_match:
                    pref_scores.append((s, p))

        pref_scores.sort(key=lambda x: x[0], reverse=True)

        max_pref_score = pref_scores[0][0] if pref_scores else 0.0
        if max_pref_score >= self.W_CONCEPT_ALIAS and not is_open:
            pref_scores = [item for item in pref_scores if item[0] > (self.W_SUBJECT_MATCH + 0.05)]

        matched_prefs = [p for _, p in pref_scores[:limit]]

        episodes = self.episodic.search_episodes(search_text, limit=limit)

        result = MemoryQueryResult(
            episodes=episodes[:limit],
            facts=matched_facts[:limit],
            preferences=matched_prefs[:limit],
        )

        from ..logging import get_logger

        logger = get_logger("MemoryRetrievalEngine")
        logger.info(
            f"Query: '{search_text}' -> found {len(matched_facts)} facts, "
            f"{len(matched_prefs)} preferences, {len(episodes)} episodes"
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


@dataclass(frozen=True)
class MemoryResult:
    episode: Episode
    score: float
    matched_keywords: list[str] = field(default_factory=list)
    intent_match: bool = False
    tool_match: bool = False
    explanation: str = ""


class MemoryRetriever:
    """Deterministic, explainable hybrid retrieval engine for AURA experiences."""

    def __init__(
        self,
        store: SQLiteMemoryStore | None = None,
        db_path: str = "data/aura.db",
        container: Any | None = None,
    ) -> None:
        from .store import MemoryStore, SQLiteMemoryStore

        if store is not None:
            self.store = store
        elif (
            container is not None and hasattr(container, "has") and container.has(SQLiteMemoryStore)
        ):
            self.store = container.resolve(SQLiteMemoryStore)
        elif container is not None and hasattr(container, "has") and container.has(MemoryStore):
            resolved = container.resolve(MemoryStore)
            if isinstance(resolved, SQLiteMemoryStore):
                self.store = resolved
            else:
                self.store = SQLiteMemoryStore(db_path=db_path)
        else:
            self.store = SQLiteMemoryStore(db_path=db_path)

        self._lock = threading.RLock()

    def _normalize_tokens(self, text: str) -> set[str]:
        """Normalizes text into clean lowercase token words, filtering out stopwords."""
        words = re.findall(r"\w+", text.lower())
        return {w for w in words if w not in STOPWORDS and len(w) > 1}

    def _compute_recency_score(self, episode_ts: datetime, now_ts: datetime) -> float:
        """Computes a bounded, monotonic recency score between 0.0 and 1.0 based on age in hours."""
        age_hours = max(0.0, (now_ts - episode_ts).total_seconds() / 3600.0)
        return 1.0 / (1.0 + (age_hours / 12.0))

    def search(
        self,
        query: str = "",
        *,
        intent_type: str | None = None,
        tools: list[str] | None = None,
        limit: int = 5,
    ) -> list[MemoryResult]:
        """Searches and ranks episodes using deterministic scoring."""
        if limit <= 0:
            return []

        with self._lock:
            all_episodes = self.store.get_episodes(limit=500)
            if not all_episodes:
                return []

            query_tokens = self._normalize_tokens(query) if query else set()
            normalized_tools = [t.lower().strip() for t in tools] if tools else []
            norm_intent = intent_type.lower().strip() if intent_type else None
            now_ts = datetime.now(UTC)

            results: list[MemoryResult] = []

            for ep in all_episodes:
                details_dict: dict[str, Any] = {}
                if ep.details:
                    try:
                        details_dict = json.loads(ep.details)
                    except Exception:
                        details_dict = {}

                # 1. Keyword Score
                ep_text = f"{ep.summary} {ep.details} {' '.join(ep.tags)}"
                ep_tokens = self._normalize_tokens(ep_text)

                matched_kw: list[str] = []
                keyword_score = 0.0
                if query_tokens:
                    matched_kw = sorted(list(query_tokens.intersection(ep_tokens)))
                    keyword_score = len(matched_kw) / len(query_tokens)

                # 2. Intent Match
                intent_match = False
                if norm_intent:
                    ep_tags = [t.lower() for t in ep.tags]
                    goal_desc = str(details_dict.get("goal_description", "")).lower()
                    if norm_intent in ep_tags or norm_intent in goal_desc:
                        intent_match = True
                intent_score = 1.0 if intent_match else 0.0

                # 3. Tool Match
                tool_match = False
                ep_tools = [str(t).lower() for t in details_dict.get("tools_used", [])]
                if normalized_tools:
                    if any(t in ep_tools for t in normalized_tools):
                        tool_match = True
                tool_score = 1.0 if tool_match else 0.0

                # 4. Outcome Bonus
                outcome = str(details_dict.get("outcome", "")).upper()
                if outcome == "SUCCESS":
                    outcome_score = 1.0
                elif outcome != "FAILED":
                    outcome_score = 0.5
                else:
                    outcome_score = 0.0

                # 5. Recency Score
                ep_ts = ep.timestamp if ep.timestamp.tzinfo else ep.timestamp.replace(tzinfo=UTC)
                recency_score = self._compute_recency_score(ep_ts, now_ts)

                # 6. Cognitive Reflection & Lesson Match
                les_val = str(details_dict.get("lesson_learned", ""))
                rc_val = str(details_dict.get("root_cause", ""))
                rec_val = str(details_dict.get("recommended_action", ""))
                lesson_text = f"{les_val} {rc_val} {rec_val}"
                lesson_tokens = (
                    self._normalize_tokens(lesson_text) if lesson_text.strip() else set()
                )
                lesson_match = bool(query_tokens and query_tokens.intersection(lesson_tokens))
                lesson_score = 0.05 if lesson_match else 0.0

                total_score = round(
                    (W_KEYWORD * keyword_score)
                    + (W_INTENT * intent_score)
                    + (W_TOOL * tool_score)
                    + (W_OUTCOME * outcome_score)
                    + (W_RECENCY * recency_score)
                    + lesson_score,
                    4,
                )

                exp_parts = [
                    f"kw_matched=[{', '.join(matched_kw)}]" if matched_kw else "kw_matched=[]",
                    f"intent_match={intent_match}",
                    f"tool_match={tool_match}",
                    f"lesson_match={lesson_match}",
                    f"outcome={outcome or 'UNKNOWN'}",
                    f"recency={recency_score:.2f}",
                    f"total_score={total_score:.3f}",
                ]
                explanation = "; ".join(exp_parts)

                results.append(
                    MemoryResult(
                        episode=ep,
                        score=total_score,
                        matched_keywords=matched_kw,
                        intent_match=intent_match,
                        tool_match=tool_match,
                        explanation=explanation,
                    )
                )

            # Deterministic sorting: score DESC, timestamp DESC, episode_id ASC
            results.sort(
                key=lambda r: (
                    -round(r.score, 4),
                    -r.episode.timestamp.timestamp(),
                    r.episode.id,
                )
            )

            return results[:limit]
