# ADR-029 — Proactive Assistant Runtime & Event-Driven Autonomy

## Status
**ACCEPTED & CERTIFIED PRODUCTION-READY**

## Context
Following the completion of Stage 22 (*Real Environment Interaction & System Observation Capability Layer*), AURA 1.6 established real host system observation (`RealSystemObservationTool`), sandboxed file operations (`RealSandboxedFileTool`), SSRF-protected HTTP retrieval (`RealHTTPRetrievalTool`), and conversational speech adapters (`ConversationalVoiceAdapter`).

However, the assistant loop remained purely reactive: executing actions only when directly invoked by a user turn. To achieve true agentic autonomy, AURA required proactive capabilities:
1. Monitoring time-based, system-metric, process-completion, and domain event triggers.
2. Maintaining persistent proactive tasks across process restarts.
3. Formulating action proposals and executing them **strictly through Stage 16 `RuntimeOrchestrator`**.
4. Guaranteeing atomic claiming and idempotency to prevent duplicate executions under concurrency or repeated events.

---

## Architectural Invariants & Decisions

### 1. Single Executive Authority
- Stage 16 `RuntimeOrchestrator` (`src/aura/cognition/scheduling/orchestration.py`) remains the **SOLE** closed-loop executive coordinator.
- Proactive condition detectors (`TimeTriggerDetector`, `SystemConditionDetector`, `ProcessConditionDetector`, `EventBusTriggerDetector`) and `ProactiveTaskEvaluator` have **ZERO** direct tool execution authority.
- The evaluator NEVER invokes `tool.execute()` or `execution_engine.execute()`. It formulates a `ToolCallProposal` and submits it to `orchestrator.execute_closed_loop(...)`.

### 2. Execution Pipeline Compliance
All proactive task actions dispatch through the complete closed-loop pipeline:
$$\text{Trigger} \xrightarrow{} \text{Proposal} \xrightarrow{} \text{Stage 16 Orchestrator} \xrightarrow{} \text{Policy (11)} \xrightarrow{} \text{Governance (10)} \xrightarrow{} \text{Execution (12)} \xrightarrow{} \text{Experience (13)} \xrightarrow{} \text{Adaptation (14)} \xrightarrow{} \text{Assurance (15)}$$

### 3. Atomic Claiming & Idempotency
To prevent race conditions, concurrent multi-thread triggers, or duplicate event executions, `ProactiveTaskStore.claim_task_for_execution(task_id)` executes an atomic SQL update:
```sql
UPDATE proactive_tasks
SET status = 'EXECUTING', updated_at = ?
WHERE task_id = ? AND status IN ('PENDING', 'ACTIVE', 'TRIGGERED');
```
If `rowcount == 1`, the task is successfully claimed and submitted to Stage 16. If `rowcount == 0`, another worker claimed it or it is inactive, preventing duplicate executions.

### 4. Zero Mutation on Rejection (`REJECTED => ZERO MUTATION`)
If Stage 11 Policy, Stage 10 Governance rate limits, or Stage 15 `SAFE_MODE` quarantine reject an operation, Stage 16 returns `RuntimeOperationState.BLOCKED`. The proactive task records status `BLOCKED`/`FAILED` with the stored failure reason, producing zero filesystem or state mutations.

### 5. Grounded Result Notifications
Notifications format real `ExecutionResult` outputs returned by Stage 16. No speculative or hallucinated notifications are produced.

---

## Consequences
- **Positive**: AURA 1.6 gains robust proactive autonomy, background task persistence, and event-driven reactions without adding secondary execution authorities or manager bloat.
- **Positive**: Tasks survive process restarts cleanly via `SQLiteMemoryStore`.
- **Positive**: 100% test coverage across 20 new Stage 23 scenario tests (`S23-01` to `S23-20`).
- **Negative**: Polling detectors require small background CPU evaluation ticks (mitigated by index optimization in SQLite).
