# MEMORY RETRIEVAL ENGINE ROOT CAUSE ANALYSIS (`memory_retrieval_root_cause.md`)

**Execution Mode**: FORENSIC ANALYSIS + IMPLEMENTATION + VALIDATION  
**Audit Target**: `MemoryRetrievalEngine` (`src/aura/memory/retrieval.py`) & FastPath Formatter  
**Status**: RESOLVED & EMPIRICALLY VERIFIED  
**Date**: 2026-08-24  

---

## 1. ROOT CAUSE SUMMARY

Empirical code traces revealed two underlying mechanics in `MemoryRetrievalEngine` that caused memory retrieval failures:

1. **Unfiltered Subject-Only Preference Matches**:
   When a user asked a specific factual query (e.g., `"¿Cuál es mi ocupación?"`), `score_preference()` assigned score **0.30** (`W_SUBJECT_MATCH`) to `color_favorito` due to the token `"mi"`. Because `max_pref_score` was 0.30 (< 0.80 threshold), `pref_scores` was not filtered out, returning `[Preference("color_favorito", "rojo")]`.
2. **Missing Key/Alias Match Check for Preferences**:
   `query()` did not verify whether a preference key or alias matched the user query tokens. As a result, preferences with no relevance to `"ocupación"` were included alongside facts.

---

## 2. CODE FIX DETAILS

In [`src/aura/memory/retrieval.py`](file:///c:/Users/Andres/Desktop/AURA/src/aura/memory/retrieval.py#L330-L348):

```python
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
```

---

## 3. EMPIRICAL VERIFICATION EVIDENCE

```text
Query: '¿Cuál es mi ocupación?' -> found 1 facts, 0 preferences, 0 episodes
Fact Returned: Fact(subject='usuario', predicate='ocupación', object_val='desarrollador')
Preference Returned: None (Suppressed)
FastPath Response: "Trabajas como desarrollador."
```
