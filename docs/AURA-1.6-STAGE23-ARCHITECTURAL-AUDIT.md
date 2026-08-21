# AURA 1.6 — STAGE 23 ARCHITECTURAL AUDIT
## Proactive Assistant Runtime & Event-Driven Autonomy

### 1. Executive Summary
This document delivers the **Phase 0 Architectural Audit** for **AURA 1.6 Stage 23: Proactive Assistant Runtime & Event-Driven Autonomy**. 

Stage 22 successfully delivered real environment interaction tools (`RealSystemObservationTool`, `RealSandboxedFileTool`, `RealHTTPRetrievalTool`) and speech turn adapters (`ConversationalVoiceAdapter`), strictly governed by Stage 16 `RuntimeOrchestrator`.

Stage 23 evolves AURA from a purely reactive assistant ("speaks when spoken to") into a proactive assistant capable of:
- Monitoring time-based, system-metric, process-completion, and EventBus triggers.
- Maintaining persistent proactive tasks across process restarts.
- Formulating action proposals and executing them **strictly through Stage 16 `RuntimeOrchestrator`**.
- Delivering grounded notifications based exclusively on confirmed `ExecutionResult` outputs.

---

### 2. Analysis of Existing Architecture & Component Contracts

#### 2.1 Event System (`src/aura/events/bus.py` & `models.py`)
- **Current State**: Thread-safe in-memory pub-sub `EventBus` using `threading.RLock()`.
- **Supported Capabilities**: `subscribe()`, `unsubscribe()`, `publish()`, `history()`, `pause()`, `resume()`.
- **Existing Event Types**: `SystemReady`, `RuntimeOperationStarted`, `RuntimeOperationCompleted`, `RuntimeOperationBlocked`, `PersistentGoalCreated`, `SessionContextUpdated`, etc.
- **Reusability in Stage 23**: `EventBusTriggerDetector` can subscribe to domain events without introducing polling overhead.

#### 2.2 Persistence & Database Architecture (`src/aura/memory/store.py`)
- **Current State**: `SQLiteMemoryStore` manages `data/aura.db` with thread-safe `threading.RLock()` and foreign keys enabled.
- **Reusability in Stage 23**: `ProactiveTaskStore` will integrate directly into `SQLiteMemoryStore`, adding tables `proactive_tasks` and `proactive_task_executions`. No second database engine or external daemon will be created.

#### 2.3 Executive Authority & Stage 16 `RuntimeOrchestrator` (`src/aura/cognition/scheduling/orchestration.py`)
- **Invariant Enforcement**: `RuntimeOrchestrator.execute_closed_loop(...)` is the **SOLE** closed-loop executive entry point.
- **Reusability in Stage 23**: When a proactive trigger conditions matches, the detector **MUST NOT** execute tools directly. It constructs a tool action proposal and submits it to `RuntimeOrchestrator.execute_closed_loop(...)`, ensuring full evaluation by:
  $$\text{Trigger} \xrightarrow{} \text{Proposal} \xrightarrow{} \text{Stage 16 Orchestrator} \xrightarrow{} \text{Policy} \xrightarrow{} \text{Governance} \xrightarrow{} \text{Execution} \xrightarrow{} \text{Experience} \xrightarrow{} \text{Adaptation} \xrightarrow{} \text{Assurance}$$

#### 2.4 Goal & Session Contexts (`src/aura/cognition/goals/` & `src/aura/cognition/session.py`)
- **GoalManager**: Manages long-term `PersistentGoal` lifecycle. Proactive tasks map optional `goal_id` to `PersistentGoal` for goal correlation.
- **SessionContext**: Tracks active session context in RAM. Proactive tasks capture `conversation_id` and `creation_turn_id` for cross-session isolation and notification routing.

---

### 3. Investigation of Key Technical Questions

1. **How `EventBus` works**: Publishes events synchronously to filtered handlers inside exception-isolated blocks. Handlers do not block the bus thread unless long operations are queued asynchronously.
2. **Real events available**: `RuntimeOperationStateChanged`, `ModuleStarted`, `ErrorOccurred`, `PersistentGoalCreated`, etc.
3. **Persistence mechanisms**: SQLite WAL database `data/aura.db` storing facts, episodes, preferences, goals, operations, audit records, and conversational turns.
4. **Goal & Session Managers**: Domain services managing goals and session context without direct execution authority.
5. **Autonomy capabilities (`src/aura/autonomy/`)**: High-level planner/executor abstractions that consume `GoalManager` and dispatch via Stage 16.
6. **Integration without secondary authority**: Proactive detectors emit `ToolCallProposal` or trigger events; they **NEVER** call `Tool.execute()`.
7. **SQLite Task Storage & Restart Recovery**: Active tasks (`PENDING`, `ACTIVE`) are queried from `proactive_tasks` table upon process startup and re-registered into the evaluation loop.
8. **Idempotency & Race Condition Prevention**: Atomic `UPDATE proactive_tasks SET status = 'EXECUTING' WHERE task_id = ? AND status IN ('PENDING', 'ACTIVE')` queries ensure that concurrent threads or duplicate events cannot execute a task twice.
9. **Task Cancellation**: Tasks marked `CANCELLED` are immediately ignored by detectors and cannot be claimed or executed.
10. **Error Handling & Failure Recovery**: Failed operation results update task status to `FAILED` with stored `failure_reason`. The grounded notification builder reports real execution failures accurately without hallucinated claims.
11. **Traceability**: All proactive operations inherit `correlation_id` and pass `goal_id` to Stage 16, maintaining unbroken trace links across operations, audit logs, and outcomes.
12. **SAFE_MODE Resilience**: If Stage 15 `SAFE_MODE` is active, Stage 16 blocks the operation immediately; the proactive task records the blocked state safely without side-effects (`REJECTED => ZERO MUTATION`).

---

### 4. Proposed Architectural Design for Stage 23

```
  +-------------------------------------------------------------------------------+
  |                          PROACTIVE TRIGGER DETECTORS                           |
  |  [TimeTrigger]      [SystemCondition]      [ProcessCondition]    [EventBus]   |
  +-------------------------------------------------------------------------------+
                                          |
                                          v (Trigger Match)
  +-------------------------------------------------------------------------------+
  |                            PROACTIVE TASK EVALUATOR                           |
  |  1. Atomic claim in SQLite (status -> EXECUTING)                              |
  |  2. Formulate Tool Proposal (action_id, tool_kwargs)                          |
  +-------------------------------------------------------------------------------+
                                          |
                                          v (Action Proposal)
  +-------------------------------------------------------------------------------+
  |                        STAGE 16 RUNTIME ORCHESTRATOR                          |
  |  Policy (11) -> Governance (10) -> Execution (12) -> Assurance (15/SAFE_MODE)|
  +-------------------------------------------------------------------------------+
                                          |
                                          v (ExecutionResult / RuntimeOperation)
  +-------------------------------------------------------------------------------+
  |                         GROUNDED NOTIFICATION ENGINE                          |
  |  1. Update ProactiveTask state (COMPLETED / FAILED) in SQLite                 |
  |  2. Generate grounded response from real ExecutionResult                      |
  |  3. Emit ProactiveNotification (ConversationalMemory / VoiceAdapter TTS)      |
  +-------------------------------------------------------------------------------+
```

---

### 5. Affected Files & Frozen Architectural Invariants

#### **New Files to Implement**:
- `src/aura/cognition/proactive/contract.py` — Strongly typed task contracts & trigger definitions.
- `src/aura/cognition/proactive/store.py` — SQLite persistent store for proactive tasks.
- `src/aura/cognition/proactive/detectors.py` — Time, system metric, process, and EventBus condition detectors.
- `src/aura/cognition/proactive/evaluator.py` — Thread-safe task evaluator submitting proposals to Stage 16.
- `src/aura/cognition/proactive/__init__.py` — Package exports.
- `tests/integration/test_aura_16_stage23_proactive_runtime.py` — Integration test suite (`S23-01` to `S23-20`).

#### **Modified Files**:
- `src/aura/memory/store.py` — Add `proactive_tasks` and `proactive_task_executions` tables to `SQLiteMemoryStore._init_db()`.
- `src/aura/cognition/scheduling/conversational_runtime.py` — Add proactive intent handling ("Recuérdame...", "Avísame cuando...", "¿Qué tareas pendientes tienes?", "Cancela esa tarea").

#### **Frozen Components (ZERO MUTATION ALLOWED)**:
- `src/aura/cognition/scheduling/orchestration.py` (Stage 16 `RuntimeOrchestrator`)
- `src/aura/cognition/scheduling/governance.py` (Stage 10 Governance)
- `src/aura/cognition/scheduling/policy.py` (Stage 11 Policy)
- `src/aura/cognition/scheduling/execution.py` (Stage 12 Execution)
- `src/aura/cognition/scheduling/assurance.py` (Stage 15 Assurance)

---

### 6. Phase 0 Audit Certification
This audit confirms that Stage 23 can be implemented cleanly over the frozen Stages 10–22 baseline without adding secondary execution authorities or violating any architectural invariant.
