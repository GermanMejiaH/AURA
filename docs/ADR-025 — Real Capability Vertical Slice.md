# ADR-025: Real Capability Vertical Slice & Product Readiness Gate

- **Status**: APPROVED
- **Date**: 2026-08-19
- **Context**: AURA 1.6 Stage 19 Real Capability Vertical Slice & Product Readiness Gate
- **Deciders**: AURA Core Architecture Team

---

## Context and Problem Statement

Following the completion and hardening of Stages 1–18, AURA 1.6 required demonstrating its **first real useful capability** operating over the frozen runtime infrastructure without creating another abstract framework layer or introducing executive authorities above Stage 16.

The goal of Stage 19 is to demonstrate a fully functional vertical slice (`RealCapabilityVerticalSlice`) executing real user turns through the existing closed-loop autonomy pipeline:
`User Turn -> IntentDetector -> GoalManager -> ToolRegistry -> Stage 16 RuntimeOrchestrator -> Action -> Output`.

---

## Decision Drivers

1. **Zero New Executive Authorities**: Stage 16 `RuntimeOrchestrator` remains the non-authoritative closed-loop coordinator.
2. **Reuse Existing Stages 10–18**: No duplication of Policy, Governance, Execution, Experience, Adaptation, or Assurance.
3. **Real Hardware Executability**: The selected vertical slice must run 100% reliably on conventional PC hardware without requiring paid cloud API keys or physical hardware peripherals.
4. **Unified ID Propagation**: Must preserve `operation_id`, `correlation_id`, `goal_id`, `action_id`, `execution_id`, `outcome_id`, `adaptation_proposal_id`.

---

## Decisions & Implementation

1. **Selected Capability Vertical Slice**:
   - **System Tool & Conversational Closed-Loop Execution (`RealCapabilityVerticalSlice`)**.
   - Integrates real input turns with built-in tools (`DateTimeTool`, `CalculatorTool`, `SystemStatusTool`).
2. **Implementation Details**:
   - Implemented `RealCapabilityVerticalSlice` and `VerticalSliceResult` in `src/aura/cognition/scheduling/vertical_slice.py`.
   - Exported in `src/aura/cognition/scheduling/__init__.py`.
3. **Integration Test Suite**:
   - Created [`tests/integration/test_aura_16_stage19_vertical_slice.py`](file:///c:/Users/Andres/Desktop/AURA/tests/integration/test_aura_16_stage19_vertical_slice.py) with 11 core vertical slice tests (`VS-01` to `VS-10` + real tool execution).
   - Result: **11/11 PASSED** (0.55s).

---

## Operational Consequences

- **Capability Readiness**: Certified as **`PASS`** for System Tool Conversational Vertical Slice.
- **Hardware Peripherals**: Physical audio input/output and vision detectors remain marked as `PARTIAL` / `MOCK` fallbacks when physical devices are absent.
- **Production Gate**: Updated [`AURA-1.6-PRODUCTION-READINESS.md`](file:///c:/Users/Andres/Desktop/AURA/docs/AURA-1.6-PRODUCTION-READINESS.md) with explicit `PASS`, `PARTIAL`, `BLOCKED`, `UNVERIFIED` classifications.
