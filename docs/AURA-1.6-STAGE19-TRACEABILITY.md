# AURA 1.6 — STAGE 19 TRACEABILITY & OBSERVABILITY SPECIFICATION

## Executive Summary
This document demonstrates how a single real user turn operation in AURA 1.6 maintains end-to-end trace correlation across all unifiable identifiers.

---

## 1. Unified Identification Schema

| Identifier Name | Originating Component | Description | Example Format |
| :--- | :--- | :--- | :--- |
| **`operation_id`** | Stage 16 `RuntimeOrchestrator` | Unique operation identifier created at `CREATED` state. | `op-a465a25f` |
| **`correlation_id`** | System / Stage 15 `RuntimeAssuranceEngine` | Unique end-to-end correlation ID linking logs, events, and audits. | `corr-e32e9643` |
| **`goal_id`** | `GoalManager` | Persistent goal ID associated with the user input turn. | `goal_f9436cf7` |
| **`action_id`** | `ToolRegistry` / `RuntimeAction` | Action or tool identifier being executed. | `datetime_tool` |
| **`execution_id`** | Stage 12 `RuntimeExecutionEngine` | Execution attempt transaction ID. | `exec-340dc995` |
| **`outcome_id`** | Stage 13 `RuntimeExperienceEngine` | Outcome memory record ID. | `exec-340dc995` |
| **`adaptation_proposal_id`** | Stage 14 `RuntimeAdaptivePolicyEngine` | Runtime adaptation proposal ID (if emitted). | `prop-datetime_tool-20260820014044` |

---

## 2. Real Execution Trace Example

```json
{
  "user_input": "¿Qué fecha y hora es hoy?",
  "intent": {
    "intent_type": "question",
    "confidence": 1.0
  },
  "trace": {
    "operation_id": "op-a465a25f",
    "correlation_id": "corr-e32e9643",
    "goal_id": "goal_f9436cf7",
    "action_id": "datetime_tool",
    "execution_id": "exec-340dc995",
    "outcome_id": "exec-340dc995",
    "adaptation_proposal_id": "prop-datetime_tool-20260820014044870975"
  },
  "pipeline_states": [
    "CREATED",
    "POLICY_EVALUATED",
    "GOVERNANCE_EVALUATED",
    "DISPATCHED",
    "EXECUTING",
    "EXPERIENCE_RECORDED",
    "ADAPTATION_CONSIDERED",
    "COMPLETED"
  ],
  "tool_execution": {
    "tool_name": "datetime_tool",
    "output": {
      "datetime_formatted": "Wednesday, August 19, 2026 20:41:00",
      "date": "2026-08-19",
      "time": "20:41:00",
      "day_of_week": "Wednesday",
      "timestamp": "2026-08-19T20:41:00.000000"
    },
    "execution_time_ms": 0.05
  },
  "assurance_status": "HEALTHY",
  "success": true
}
```

---

## 3. Observability Audit Trail in SQLite

All audit records recorded during closed-loop execution share the single `correlation_id`:
```sql
SELECT audit_id, timestamp, correlation_id, stage, event_type, action, outcome
FROM runtime_audit_records
WHERE correlation_id = 'corr-e32e9643';
```
Output:
`audit-88a21f | 2026-08-19T20:41:00Z | corr-e32e9643 | STAGE_16 | CLOSED_LOOP_COMPLETED | datetime_tool | SUCCESS`
