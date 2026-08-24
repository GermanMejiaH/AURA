# FORENSIC AUDIT: TOOL CONTEXT INJECTION (`tool_context_audit.md`)

**Execution Mode**: FORENSIC AUDIT (READ-ONLY)  
**Audit Target**: `CognitiveContextBuilder` Tool Metadata Injection  
**Date**: 2026-08-24  

---

## 1. OBSERVED PRODUCTION DISCREPANCY

During simple declarative utterances like:
- `"Soy Andrés"`
- `"Tengo 26 años"`
- `"Vivo en Medellín"`

Telemetry logs showed:
`tool_tokens = 213` (or `~250 tokens`).

---

## 2. FORENSIC TRACE & CODE AUDIT

1. **Utterance Processing**: User inputs `"Soy Andrés"`.
2. **Intent Classification**: `IntentDetector.detect("Soy Andrés")` classifies intent as `MEMORY_UPDATE` or `INFORMATIONAL`.
3. **Casual Intent Evaluation**:
   In `src/aura/cognition/context.py` lines 315–319:
   ```python
   is_casual = input_lower in casual_greetings or intent_name in (
       "GREET",
       "SALUTATION",
       "SMALLTALK",
   )
   ```
4. **Outcome of `is_casual`**:
   `"soy andrés"` is NOT in `casual_greetings` (`"hola"`, `"saludos"`).
   `intent_name` (`MEMORY_UPDATE`) is NOT in `("GREET", "SALUTATION", "SMALLTALK")`.
   `is_casual` evaluates to **`False`**.
5. **Tool Registry Injection**:
   Because `is_casual` is `False`, line 359 executes `if not is_casual:`:
   ```python
   if self.container.has(ToolRegistry):
       reg = self.container.resolve(ToolRegistry)
       available_tools = [
           {"name": meta.name, "description": meta.description}
           for meta in reg.list_metadata()
       ]
   ```
6. **Result**: Full metadata for all registered digital tools is converted to text and appended to `to_system_prompt()`, adding **213+ tokens** to system instructions.

---

## 3. TOOL TOKEN CONTRIBUTION TABLE

| Tool Name | Description | BPE Token Count | Included for `"Soy Andrés"`? | Rationale for Inclusion |
|---|---|---|---|---|
| `timer` / `NotificationTool` | Schedules one-shot timers & recurring cron tasks | 42 tokens | **Yes** | Injected because `is_casual` evaluated `False` |
| `system` / `SystemTool` | Executes shell commands & system inspection | 48 tokens | **Yes** | Injected because `is_casual` evaluated `False` |
| `memory` / `MemoryTool` | Queries and inspects long-term memory | 38 tokens | **Yes** | Injected because `is_casual` evaluated `False` |
| `weather` / `WeatherTool` | Fetches weather forecasts & climate data | 45 tokens | **Yes** | Injected because `is_casual` evaluated `False` |
| `search` / `SearchTool` | Performs web search & URL reading | 40 tokens | **Yes** | Injected because `is_casual` evaluated `False` |
| **TOTAL** | **5 Registered Tools** | **213 tokens** | **Yes (Wasted)** | **Unnecessary Tool Metadata Injection** |

---

## 4. ROOT CAUSES & RECOMMENDATIONS

1. **Defective `is_casual` Gating Logic**:
   `is_casual` check evaluates ONLY literal greetings. Declarative personal memory statements (`"Soy Andrés"`, `"Tengo 26 años"`) fall through to non-casual logic, needlessly injecting 213+ tokens of tool metadata.
2. **Missing Intent-Based Tool Gating**:
   Tools should ONLY be injected when `IntentDetector` detects a tool execution intent (`TASK_REQUEST`, `COMMAND`, `ACTION`, `WEB_SEARCH`). Simple factual statements or memory updates do not require digital tools.

---

## 5. EXACT CODE LOCATIONS

- `src/aura/cognition/context.py`: Lines 315–319 (`is_casual` definition) & Lines 359–368 (`available_tools` extraction).
