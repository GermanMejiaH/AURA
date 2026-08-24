# HISTORY WINDOW REGRESSION AUDIT (`history_window_regression.md`)

**Execution Mode**: READ-ONLY FORENSIC ANALYSIS + ROOT CAUSE INVESTIGATION  
**Status**: AUDIT COMPLETE  
**Date**: 2026-08-24  

---

## 1. AUDIT OBJECTIVE

Investigate why logs during field pilot operation show `history_turns > 4` (e.g. 6, 8, or 12 turns), despite Stage 26.3F setting the default history limit to 4 turns.

---

## 2. CODE PATH TRACE

The history window calculation logic was traced to `get_max_history_turns()` in [`src/aura/cognition/context.py:L32-L91`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/context.py#L32-L91):

```python
def get_max_history_turns(intent: Any | None, input_text: str = "") -> int:
    ...
    if any(kw in input_lower for kw in ("resumir", "resumen", "recap", "summary", "historial", "anterior", "conversación")):
        return 12

    if input_lower in casual_greetings or intent_type_str in ("GREET", "GREETING", "SALUTATION", "SMALLTALK"):
        return 2
    elif intent_type_str in ("QUESTION", "INFORMATIONAL", "CONFIRMATION", "CANCELLATION"):
        return 6
    elif intent_type_str in ("TASK_REQUEST", "PLAN", "GOAL", "COMMAND", "AUTONOMY", "ACTION"):
        return 8
    elif intent_type_str in ("REFLECT", "LEARN", "MEMORY_QUERY", "AUTOBIOGRAPHICAL", "MEMORY_UPDATE"):
        return 12
    return 4
```

---

## 3. FORENSIC RESPONSES TO AUDIT QUESTIONS

1. **Which code path produces `history_turns > 4`?**:
   - In [`src/aura/cognition/context.py:L225`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/context.py#L225) and [`L470`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/context.py#L470), `CognitiveContextBuilder.build()` calls `get_max_history_turns(detected_intent, input_text)`.
   - When intent is classified as `QUESTION` or `CONFIRMATION`, `max_h_turns` returns **6**.
   - When intent is classified as `TASK_REQUEST` or `COMMAND`, `max_h_turns` returns **8**.
   - When intent is classified as `MEMORY_QUERY` or `LEARN`, or if input text contains words like `"conversación"` or `"historial"`, `max_h_turns` returns **12**.

2. **Is `history_turns > 4` expected or a bug?**:
   - It is **by design (adaptive history windowing)**, NOT a functional regression bug.
   - Stage 26.3F set default fall-through history to 4 turns, but designed intent-based expansion for complex queries (questions = 6, commands = 8, memory queries = 12).

3. **Does it contribute to payload inflation?**:
   - **YES (SIGNIFICANT IMPACT)**. When history window expands to 12 turns, `to_formatted_prompt()` formats 12 turns (up to 24 user + assistant dialogue turns).
   - If past turns contained large tool execution outputs, system status reports, or long responses, 12 turns can easily add **2,000 to 5,000 tokens** to the LLM prompt, triggering HTTP 413 errors on cloud API providers.
