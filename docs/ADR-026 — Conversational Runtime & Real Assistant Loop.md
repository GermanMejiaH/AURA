# ADR-026 — Conversational Runtime & Real Assistant Loop

* **Status**: `ACCEPTED`  
* **Date**: 2026-08-20  
* **Stage**: Stage 20 — Conversational Runtime & Real Assistant Loop  

---

## Context

Following Stage 19's single-turn vertical slice certification, AURA required evolving into a multi-turn, context-aware conversational loop (`ConversationalRuntime`) capable of resolving anaphora references ("¿Y qué día es?", "Súmale 20") across user interactions while maintaining SQLite persistence and strict non-negotiable safety boundaries.

---

## Decision

1. **Implement `ConversationalRuntime`**:
   - Acts as the unified multi-turn entry point.
   - Integrates `ConversationalMemory` (SQLite turn store), `SessionManager` (RAM context), `AnaphoraResolver` (contextual entity resolution), `IntentDetector`, and `GoalManager`.

2. **Strict Authority Boundary**:
   - Cognitive providers and LLMs act strictly as proposal generators (`tool_name`, `tool_kwargs`).
   - Executive authority remains 100% within Stage 16 `RuntimeOrchestrator.execute_closed_loop(...)`.
   - Actions MUST pass through Policy, Governance, Execution, Experience, Adaptation, and Assurance.

3. **Grounded Natural Responses**:
   - Responses are generated strictly from real `ExecutionResult` outputs.
   - Illusions, hallucinations, or unverified output claims are strictly prohibited.

4. **Multi-Turn Context & Isolation**:
   - Multi-turn turn tracking and recent output caching allow contextual continuations (e.g. math operations over previous outputs).
   - Session isolation guarantees no cross-session contamination across concurrent user sessions.

---

## Consequences

* **Positive**:
  - Full end-to-end multi-turn capability certified across 20 integration scenarios.
  - Process restarts cleanly reconstruct conversation context from SQLite.
  - Zero executive authority granted to LLMs/cognitive providers.
  - Full correlation trace preserved across turn, goal, operation, execution, outcome, and turn ID.

* **Negative**:
  - Requires maintaining thread-safe SQLite connection handles across process turns.
