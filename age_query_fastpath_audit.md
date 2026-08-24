# FORENSIC AUDIT: AGE QUERY FAST-PATH FAILURE (`age_query_fastpath_audit.md`)

**Execution Mode**: FORENSIC AUDIT (READ-ONLY)  
**Audit Target**: `ControlIntentDetector.DIRECT_MEMORY_PATTERNS` & FastPath Routing  
**Date**: 2026-08-24  

---

## 1. OBSERVED PRODUCTION DISCREPANCY

When asking:
`"¿Cuántos años tengo?"`

- **Observed Behavior**: Did NOT enter 0-LLM FastPath. Built full LLM `CognitiveContext`, invoked cloud provider LLM REST call, generated `HTTP 413 Request Entity Too Large` / `HTTP 429 Rate Limit` error.
- **Expected Behavior**: FastPath intercept (0 LLM calls) returning: `"Tu edad es 26."` or `"Tienes 26 años."`.

---

## 2. FORENSIC TRACE

1. **User Utterance**: `"¿Cuántos años tengo?"`
2. **Text Normalization**:
   `ControlIntentDetector.normalize_text("¿Cuántos años tengo?")` -> `"cuantos anos tengo"` (or `"cuantos anios tengo"`).
3. **Pattern Matching against `DIRECT_MEMORY_PATTERNS`**:
   `ControlIntentDetector` iterates over `DIRECT_MEMORY_PATTERNS` in `src/aura/cognition/intent.py` lines 86–92:
   ```python
   DIRECT_MEMORY_PATTERNS: tuple[str, ...] = (
       r"\bcu[aá]l\s+es\s+mi\b",
       r"\bc[oó]mo\s+me\s+llamo\b",
       r"\bqui[eé]n\s+soy\b",
       r"\bqu[eé]\s+sabes\s+de\s+m[ií]\b",
       r"\bsabes\s+cu[aá]l\s+es\s+mi\b",
   )
   ```
4. **Result**:
   `"cuantos anos tengo"` matches **NONE** of the 5 patterns in `DIRECT_MEMORY_PATTERNS`.
5. **FastPath Check Outcome**:
   `ControlIntentDetector.is_direct_memory_query("¿Cuántos años tengo?")` returns `False`.
6. **LLM Fallback**:
   The request is routed to `CognitionModule.process_cognitive_cycle()`, constructing full context and triggering an expensive LLM API call.

---

## 3. COMPARATIVE QUERY EVALUATION TABLE

| Query Utterance | Normalized Text | `DIRECT_MEMORY_PATTERNS` Match | FastPath Active | Action Taken |
|---|---|---|---|---|
| `"¿Quién soy?"` | `"quien soy"` | `r"\bqui[eé]n\s+soy\b"` | **True** | 0-LLM FastPath executed |
| `"¿Cuántos años tengo?"` | `"cuantos anos tengo"` | **None** | **False** | LLM cycle called → 413 Error |
| `"¿Dónde vivo?"` | `"donde vivo"` | **None** | **False** | LLM cycle called → 413 Error |
| `"¿Qué estudio?"` | `"que estudio"` | **None** | **False** | LLM cycle called → 413 Error |
| `"¿Dónde trabajo?"` | `"donde trabajo"` | **None** | **False** | LLM cycle called → 413 Error |

---

## 4. ROOT CAUSE DETERMINATION

1. **Pattern Omission in `ControlIntentDetector`**:
   `DIRECT_MEMORY_PATTERNS` in `src/aura/cognition/intent.py` contains regexes for `"quién soy"`, `"cómo me llamo"`, and `"cuál es mi"`, but completely lacks regex patterns for age (`"cuántos años tengo"`), location (`"dónde vivo"`), studies (`"qué estudio"`), and occupation (`"dónde trabajo"`).
2. **Bypass of FastPath Routing**:
   As a direct consequence, natural user queries about age or location fail the FastPath test, forcing AURA to construct an un-capped prompt payload and send it to the LLM API, triggering 413 payload limit errors.

---

## 5. EXACT CODE LOCATIONS

- `src/aura/cognition/intent.py`: Lines 86–92 (`DIRECT_MEMORY_PATTERNS`) & Lines 167–177 (`is_direct_memory_query`).
- `src/aura/audio/autonomous_agent.py`: Lines 194–235 (`FastPath execution check`).
