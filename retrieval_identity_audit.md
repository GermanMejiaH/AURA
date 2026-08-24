# FORENSIC AUDIT: MEMORY RETRIEVAL & IDENTITY RANKING (`retrieval_identity_audit.md`)

**Execution Mode**: FORENSIC AUDIT (READ-ONLY)  
**Audit Target**: `MemoryRetrievalEngine` & `AutonomousVoiceAgent` FastPath  
**Date**: 2026-08-24  

---

## 1. OBSERVED PRODUCTION DISCREPANCY

When asking:
`"¿Quién soy?"`

- **Observed Log Output**:
  `MemoryRetrievalEngine: Query: '¿Quién soy?' -> found 5 facts, 1 preferences`
- **Observed Response**: `"Tu color_favorito es el rojo."` (or single arbitrary fact).
- **Expected Response**: Identity profile response returning:
  `"Eres Andrés, tienes 26 años, vives en Medellín, estudias ingeniería de software y trabajas como desarrollador."`

---

## 2. EXECUTION PATH TRACE

1. **User Utterance**: `"¿Quién soy?"`
2. **Intent Classification**:
   `ControlIntentDetector.is_direct_memory_query("¿Quién soy?")` returns `True` (matches `r"\bqui[eé]n\s+soy\b"`).
3. **Retrieval Dispatch**:
   `AutonomousVoiceAgent` calls `mem_mod.retrieval.query("¿Quién soy?")`.
4. **Token Normalization**:
   `search_text = "¿Quién soy?"` -> `query_tokens = {"quien", "soy"}`.
5. **Recall Pattern Evaluation**:
   `_is_open_recall_query("¿Quién soy?", {"quien", "soy"})` evaluates `True` (matches `r"\bqui[eé]n\s+soy\b"`).
6. **Fact & Preference Scoring**:
   - `score_fact()` for `nombre=Andrés`:
     - `norm_pred` = `"nombre"`. `"nombre"` not in `query_tokens`.
     - `aliases` = `{"nombre", "llamo", "llamaron"}`. None in `query_tokens`.
     - `personal_tokens` match: `"soy"` in `personal_tokens` -> `score += W_SUBJECT_MATCH` (**0.30**).
     - Score = **0.30**.
   - `score_fact()` for `edad=26`, `ciudad=Medellín`, `actividad=...`, `ocupacion=...`: All score **0.30**.
   - `score_preference()` for `color_favorito=rojo`:
     - `personal_tokens` match: `"soy"` in `personal_tokens` -> `score += W_SUBJECT_MATCH` (**0.30**).
     - Score = **0.30**.
7. **FastPath Formatting**:
   In `AutonomousVoiceAgent.py` lines 205-220:
   ```python
   top_fact = res_retrieval.facts[0] if res_retrieval.facts else None
   top_pref = res_retrieval.preferences[0] if res_retrieval.preferences else None

   if top_fact and top_fact.confidence >= 0.85:
       ans = f"Tu {top_fact.predicate} es {top_fact.object_val}."
   elif top_pref:
       ans = f"Tu preferencia para {top_pref.key} es {top_pref.value}."
   ```

---

## 3. ROOT CAUSE DETERMINATION

1. **Equal Baseline Tie (0.30 Score)**:
   For open identity queries like `"¿Quién soy?"`, all identity facts (`nombre`, `edad`, `ciudad`, `actividad`, `ocupacion`) and preferences tie at score **0.30** because `"quien"` and `"soy"` match only `W_SUBJECT_MATCH` without matching predicate concept aliases.
2. **Single Fact Selection Defect**:
   `AutonomousVoiceAgent` evaluates only `res_retrieval.facts[0]` (a single item). If `facts` list sorting places a preference first or if `top_fact` is arbitrarily ordered, it returns a single predicate like `color_favorito` or `nombre` instead of concatenating the complete identity profile.

---

## 4. EXACT CODE LOCATIONS

- `src/aura/memory/retrieval.py`: Lines 223–278 (`score_fact`) & Lines 280–308 (`score_preference`) & Lines 310–354 (`query`).
- `src/aura/audio/autonomous_agent.py`: Lines 205–227 (`FastPath response selection`).
