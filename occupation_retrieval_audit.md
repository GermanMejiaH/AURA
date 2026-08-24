# OCCUPATION RETRIEVAL AUDIT (`occupation_retrieval_audit.md`)

**Execution Mode**: IMPLEMENTATION + VALIDATION  
**Audit Target**: `"¿Cuál es mi ocupación?"` Retrieval & FastPath Selection  
**Status**: PASSED  
**Date**: 2026-08-24  

---

## 1. DEFECT DESCRIPTION

- **Observed Behavior**: Asking `"¿Cuál es mi ocupación?"` returned `"Tu color_favorito es el rojo."`.
- **Root Causes Identified**:
  1. `score_preference()` assigned `W_SUBJECT_MATCH` (0.30) to `color_favorito` because of the word `"mi"`.
  2. Predicate predicate string matching in `AutonomousVoiceAgent` used strict equality (`pred == "ocupacion"`) without accent normalization, causing stored predicate `"ocupación"` to miss custom response formatting.
  3. `top_fact.confidence >= 0.85` check skipped facts with confidence <= 0.84, falling back to preferences.

---

## 2. REFACTORING & FIXES APPLIED

1. **Preference Gating**: Enforced `has_key_match` in `MemoryRetrievalEngine.query()`, suppressing unrelated preferences on specific factual queries.
2. **Predicate Normalization**: Applied `normalize_text(top_fact.predicate)` in `AutonomousVoiceAgent` to ensure `"ocupación"` matches `"ocupacion"`.
3. **Alias Matching for Fact Answers**:
   ```python
   norm_pred = normalize_text(top_fact.predicate)
   if "ocupacion" in norm_pred or "trabajo" in norm_pred or "profesion" in norm_pred or "empleo" in norm_pred:
       ans = f"Trabajas como {val}."
   ```

---

## 3. VERIFICATION LOG

```text
Query: '¿Cuál es mi ocupación?'
  • Fact Returned: predicate='ocupación', object_val='desarrollador'
  • Preferences Returned: []
  • FastPath Output: "Trabajas como desarrollador."
  • Status: PASSED (100% Correct Output)
```
