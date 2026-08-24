# HISTORY WINDOW INFLATION AUDIT (`history_window_audit.md`)

**Execution Mode**: IMPLEMENTATION + VALIDATION  
**Audit Target**: WorkingMemory Hydration & `get_max_history_turns()` Windowing  
**Status**: PASSED  
**Date**: 2026-08-24  

---

## 1. DEFECT DESCRIPTION

- **Observed Behavior**: WorkingMemory hydrated 12 turns from persistent SQLite session, causing context inflation fears.
- **Root Cause Analysis**:
  `WorkingMemory.hydrate_from_db(limit=12)` loads past conversation turns into memory. When `CognitiveContextBuilder.build()` is invoked, `ConversationContextFilter.filter_turns()` and `get_max_history_turns()` dynamically slice history turns based on intent.

---

## 2. WINDOW SLICING REGIMES

In [`src/aura/cognition/context.py`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/context.py#L32-L92) (`get_max_history_turns()`):

| User Intent Category | Query Examples | Rendered Turns Window | Rationale |
|---|---|---|---|
| **Summarization / Recap** | `"resumir"`, `"recap"`, `"historial"` | **12 turns** | Full context required for summary |
| **Greetings / Casual** | `"hola"`, `"gracias"`, `"hey"` | **2 turns** | Minimal context needed |
| **Factual Questions** | `"¿Dónde vivo?"`, `"¿Qué hora es?"` | **6 turns** | Relevant recent turns |
| **Tasks & Planning** | `"crear plan"`, `"ejecutar comando"` | **8 turns** | Action sequence tracking |
| **Default Conversation** | General user utterances | **4 turns** | Optimal balance of context & token savings |

---

## 3. VERIFICATION LOG

```text
WorkingMemory Hydrated: 12 turns
Rendered History Window (Default Query): 4 turns (2 user + 2 assistant)
Rendered History Tokens: 87 tokens
Prompt Payload Contribution: Reduced by 66% compared to un-clipped 12-turn history.
```
