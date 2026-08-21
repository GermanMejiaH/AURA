# AURA 1.6 — STAGE 20 ARCHITECTURAL AUDIT & CONVERSATIONAL RUNTIME DESIGN

## Executive Summary
This document records the Phase 0 Architectural Audit for **AURA 1.6 Stage 20: Conversational Runtime & Real Assistant Loop**.
It defines how the single-turn vertical slice demonstrated in Stage 19 (`RealCapabilityVerticalSlice`) is evolved into a multi-turn, context-aware, persistent conversational loop without introducing new executive authorities above Stage 16 or altering frozen contracts in Stages 10–19.

---

## 1. Current State Assessment
- **Stage 19 Baseline**: Single-turn closed-loop execution runner `RealCapabilityVerticalSlice` connecting `User Input` -> `IntentDetector` -> `GoalManager` -> `ToolRegistry` -> `Stage 16 RuntimeOrchestrator` -> `Tool Output`.
- **Existing Persistence**: SQLite tables (`memory_sessions`, `conversation_turns`, `runtime_operations`, `runtime_audit_records`, `runtime_checkpoints`).
- **Existing Cognitive & Context Modules**:
  - `SessionContext` & `SessionManager` (`src/aura/cognition/session.py`): In-RAM volatile session state.
  - `ConversationalMemory` (`src/aura/memory/conversational.py`): Thread-safe SQLite session/turn store.
  - `AnaphoraResolver` & `ConversationContextFilter` (`src/aura/cognition/conversation_context.py`): Deterministic resolution of contextual references ("¿Y qué día es?", "Súmale 20").
  - `ToolOrchestrator` (`src/aura/cognition/tool_orchestrator.py`): Safe tool proposal & parameter extraction.
  - `LLMProvider` abstractions (`GeminiLLMProvider`, `OpenAILLMProvider`, `MockLLMProvider`).

---

## 2. Reusable Components vs Missing Components

### Reusable Components (100% Real Code)
1. **Stage 16 `RuntimeOrchestrator`**: Non-authoritative closed-loop coordinator across all 8 operational states.
2. **Stage 10 `RuntimeGovernanceEngine`**: Scope authority (`UNRESTRICTED`, `READ_ONLY`) & rate-limiting.
3. **Stage 11 `RuntimePolicyEngine`**: Priority aging & conflict resolution.
4. **Stage 12 `RuntimeExecutionEngine`**: Transactional step execution, timeout & `rollback_fn`.
5. **Stage 13 `RuntimeExperienceEngine`**: Outcome memory & execution metrics recording in SQLite.
6. **Stage 14 `RuntimeAdaptivePolicyEngine`**: Adaptation proposal evaluation (`requires_operator_approval=True`).
7. **Stage 15 `RuntimeAssuranceEngine`**: Checkpointing, audit logging & `SAFE_MODE` quarantine.
8. **`ConversationalMemory`**: Persistent SQLite session and turn history store.
9. **`SessionManager`**: Active session topic, task, turn count tracking.
10. **`AnaphoraResolver`**: Deterministic resolution of pronouns and contextual references between turns.
11. **`ToolRegistry` & Built-in Tools**: `DateTimeTool`, `CalculatorTool`, `SystemStatusTool`.

### Missing Components (To Be Implemented in Stage 20)
1. **`ConversationalRuntime` / `ConversationalAssistantLoop`**: Multi-turn conversational orchestrator linking conversation turns, context resolution, tool proposal, Stage 16 closed-loop execution, persistent turn recording, and natural response generation.
2. **Natural Response Generator**: Constructs clear, contextually accurate responses grounded strictly in the real execution result produced by Stage 12/13.
3. **Conversation & Turn Correlation Mapping**: Formal mapping extending unified trace correlation across `conversation_id`, `turn_id`, `correlation_id`, `operation_id`, `goal_id`, `action_id`, `execution_id`, `outcome_id`, `adaptation_proposal_id`.

---

## 3. Authority Boundaries & LLM Governance

```
                    ┌─────────────────────────┐
                    │       USER INPUT        │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   ConversationalTurn    │
                    │   (Turn & Session ID)   │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   Cognitive / LLM       │
                    │   (Understanding ONLY)  │
                    │  *PROPOSES* Tool Call   │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Context & Anaphora      │
                    │ Resolution              │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   Goal & Action Plan    │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   RuntimeOrchestrator   │
                    │  (Stage 16 Coordinator) │
                    └────────────┬────────────┘
                                 │
                   ┌─────────────┴─────────────┐
                   ▼                           ▼
            Stage 11 Policy           Stage 10 Governance
                   └─────────────┬─────────────┘
                                 ▼
                         Stage 12 Execution
                                 ▼
                         Stage 13 Experience
                                 ▼
                         Stage 14 Adaptation
                                 ▼
                         Stage 15 Assurance
                                 ▼
                    ┌─────────────────────────┐
                    │  Natural Response Gen.  │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │       USER OUTPUT       │
                    └─────────────────────────┘
```

### Strict Non-Negotiable Governance Rules:
- **LLM Has ZERO Executive Authority**: The LLM interprets natural language, extracts intent, and proposes tool parameters. It cannot execute tools directly, bypass governance, modify policy, alter assurance, or elevate scope.
- **Stage 16 Orchestrator is the Central Coordinator**: All tool proposals must pass through `RuntimeOrchestrator` -> Policy -> Governance -> Execution.
- **Stage 14 HITL Intact**: Operator approval (`APPROVED != APPLIED`) remains mandatory for policy adaptations.
- **Stage 15 SAFE_MODE Intact**: Quarantine blocks execution immediately.

---

## 4. File Modification Boundaries

### Files to Create in Stage 20:
- `src/aura/cognition/scheduling/conversational_runtime.py` `[NEW]`
- `tests/integration/test_aura_16_stage20_conversational_runtime.py` `[NEW]`
- `docs/AURA-1.6-STAGE20-ARCHITECTURAL-AUDIT.md` `[NEW]`
- `docs/AURA-1.6-STAGE20-CONVERSATIONAL-TRACEABILITY.md` `[NEW]`
- `docs/ADR-026 — Conversational Runtime & Real Assistant Loop.md` `[NEW]`

### Files to Update in Stage 20:
- `src/aura/cognition/scheduling/__init__.py` `[MODIFY]` (Export Stage 20 symbols)
- `docs/AURA-1.6-PRODUCTION-READINESS.md` `[MODIFY]`
- `walkthrough.md` `[MODIFY]`

### Files FROZEN — DO NOT MODIFY:
- Stage 10 Governance (`src/aura/cognition/scheduling/governance.py`)
- Stage 11 Policy (`src/aura/cognition/scheduling/resolution.py`, `policy.py`)
- Stage 12 Execution (`src/aura/cognition/scheduling/execution.py`)
- Stage 13 Experience (`src/aura/cognition/scheduling/experience.py`)
- Stage 14 Adaptation (`src/aura/cognition/scheduling/adaptation.py`)
- Stage 15 Assurance (`src/aura/cognition/scheduling/assurance.py`)
- Stage 16 Orchestration (`src/aura/cognition/scheduling/orchestration.py`)

---

## 5. Phased Implementation Plan

- **Phase 0**: Architectural Audit & User Approval (This document & `implementation_plan.md`).
- **Phase 1**: Implement `ConversationalRuntime` & `ConversationalTurnResult` in `src/aura/cognition/scheduling/conversational_runtime.py`.
- **Phase 2**: Integration Test Suite (`CV-01` to `CV-20` + Reality Validation) in `tests/integration/test_aura_16_stage20_conversational_runtime.py`.
- **Phase 3**: Traceability & Observability specification in `docs/AURA-1.6-STAGE20-CONVERSATIONAL-TRACEABILITY.md`.
- **Phase 4**: Production Gate & ADR-026 documentation.
- **Phase 5**: Full verification pipeline (pytest 1152+ tests, ruff format, ruff check, mypy).

---

## 6. Meaning of REAL vs MOCKED
- **REAL**:
  - `ConversationalRuntime` multi-turn loop
  - `ConversationalMemory` (SQLite session/turn persistence)
  - `SessionManager` in-RAM turn tracking
  - `AnaphoraResolver` contextual reference resolution
  - Stage 10–16 Governance, Policy, Execution, Experience, Adaptation, Assurance, Orchestration
  - `DateTimeTool`, `CalculatorTool`, `SystemStatusTool`
- **MOCKED / FALLBACK**:
  - Cloud LLM API calls when `GEMINI_API_KEY`/`OPENAI_API_KEY` are unconfigured (`MockLLMProvider`)
  - Microphone/speaker hardware streams when physical audio devices are absent (`MockSTTProvider`/`MockTTSProvider`)
- **UNVERIFIED**:
  - Physical vision sensors and robotics actuators requiring external hardware.
