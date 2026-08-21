# AURA 1.6 — STAGE 22 ARCHITECTURAL AUDIT
**Real Assistant Capability Expansion & Environment Interaction**
**Phase 0 — Comprehensive System Inspection & Architectural Assessment**

---

## 1. Executive Summary

Stage 22 defines the evolution of **AURA 1.6** from a persistent cognitive-conversational runtime (Stage 21) into a full-featured, environment-aware assistant.

Following a thorough audit of `src/aura/`, `tests/`, existing ADRs, and production readiness matrices, this document establishes the architectural baseline, identifies existing capabilities vs. gaps, evaluates trust boundaries, and defines the recommended scope for Stage 22.

---

## 2. Current Stage 21 Architecture

The verified Stage 21 architecture operates as follows:

```
[User Input]
     │
     ▼
[ConversationalRuntime] ──► [ConversationalMemory (SQLite)]
     │                  ──► [AnaphoraResolver & IntentDetector]
     ▼
[LLMProvider / GeminiLLMProvider] (Cognitive Provider — ZERO Executive Authority)
     │  (Outputs untrusted CognitiveTurnInterpretation & ToolCallProposal)
     ▼
[ToolRegistry.validate_parameters(...)] (Schema & Type Validation)
     │
     ▼
[Stage 16 RuntimeOrchestrator] (SOLE Executive Authority)
     │
     ├──► Stage 11: RuntimePolicyEngine (ALLOW / BLOCK / CONFIRM)
     ├──► Stage 10: RuntimeGovernanceEngine (Authority Scopes & Rate Limits)
     ├──► Stage 12: RuntimeExecutionEngine (Transactional Execution & Rollback)
     ├──► Stage 13: RuntimeExperienceEngine (Outcomes & Performance Telemetry)
     ├──► Stage 14: RuntimeAdaptivePolicyEngine (HITL: APPROVED != APPLIED)
     └──► Stage 15: RuntimeAssuranceEngine (Point-in-Time Checkpoints & SAFE_MODE)
     │
     ▼
[Authoritative ExecutionResult]
     │
     ▼
[LLMProvider.generate_grounded_response(...)] (Strictly Grounded Response Formatting)
     │
     ▼
[User Output]
```

### Critical Invariants Verified:
1. **Sole Executive Coordinator**: `RuntimeOrchestrator` (Stage 16) is the single point of execution authority.
2. **Zero Authority for LLMs**: LLMs generate untrusted proposals only. LLMs cannot invoke tools directly.
3. **Strict Validation**: Tool proposals pass through `ToolRegistry.validate_parameters(...)` before reaching Stage 16.
4. **Governed Closed Loop**: All tool executions pass through Stage 10 Governance, Stage 11 Policy, Stage 12 Execution, Stage 13 Experience, Stage 14 Adaptation, and Stage 15 Assurance.
5. **Grounded Responses**: Natural language outputs are grounded strictly in real `ExecutionResult` data.
6. **Deterministic Offline Fallback**: In the absence of external API keys, the system falls back to Stage 20 deterministic rules without crashing.

---

## 3. Stage 10–21 Capability Baseline

- **Stage 10 (Governance)**: Scope-based access control (`FULL`, `READ_ONLY`, `DISABLED`) and sliding-window rate limiting.
- **Stage 11 (Policy)**: Context-aware rules evaluating action risk levels and parameters.
- **Stage 12 (Execution)**: Transactional execution with reverse-order rollback and compensation functions.
- **Stage 13 (Experience)**: Operational metrics tracking and outcome evaluation.
- **Stage 14 (Adaptation)**: Human-in-the-Loop policy mutation proposals (`APPROVED != APPLIED`, `REJECTED => ZERO MUTATION`).
- **Stage 15 (Assurance)**: Health snapshots, state checkpoints, and global `SAFE_MODE` quarantine.
- **Stage 16 (Orchestration)**: Single closed-loop executive coordinator (`execute_closed_loop(...)`).
- **Stage 17 (Integration)**: End-to-end multi-stage pipeline integration tests.
- **Stage 18 (Reality)**: System verification on real host OS without mock shortcut stubs.
- **Stage 19 (Vertical Slice)**: System tool capability slice (`DateTimeTool`, `CalculatorTool`, `SystemStatusTool`).
- **Stage 20 (Conversational Runtime)**: Multi-turn conversational session memory and anaphora resolution.
- **Stage 21 (Cognitive Provider)**: Real Gemini LLM integration (`GeminiLLMProvider`) with schema validation and grounded response formatting.

---

## 4. Existing Capability Inventory

| Domain / Subsystem | Current Status | Implemented Component | Classification |
| :--- | :--- | :--- | :--- |
| **System Date & Time** | Real Python `datetime` module | `DateTimeTool` | `REAL + PRODUCTION READY` |
| **Math Evaluation** | Safe AST node evaluator | `CalculatorTool` (`SafeASTMathEvaluator`) | `REAL + PRODUCTION READY` |
| **Conversational Memory** | SQLite persistent store | `ConversationalMemory` / `SQLiteMemoryStore` | `REAL + PRODUCTION READY` |
| **Cognitive Reasoning** | Google GenAI SDK integration | `GeminiLLMProvider` / `MockLLMProvider` | `REAL + PRODUCTION READY` |
| **Closed-Loop Engine** | Stage 10–16 Governance pipeline | `RuntimeOrchestrator` & Stage 10–15 Engines | `REAL + PRODUCTION READY` |
| **Event Bus** | Thread-safe in-memory pub/sub | `EventBus` (`threading.RLock`) | `REAL + PRODUCTION READY` |
| **System Status** | Hardcoded status dict | `SystemStatusTool` | `REAL + PARTIAL` |
| **Speech-to-Text (STT)** | `faster_whisper` wrapper | `FasterWhisperSTTProvider` / `MockSTTProvider` | `REAL + PARTIAL` |
| **Text-to-Speech (TTS)** | `edge-tts` / SAPI wrapper | `EdgeTTSProvider` / `MockTTSProvider` | `REAL + PARTIAL` |
| **Audio Hardware I/O** | `sounddevice` wrappers | `SoundDeviceInputProvider` / `SoundDeviceOutputProvider` | `REAL + PARTIAL` |
| **Wake Word Detection** | Open-source keyword detector | `WhisperWakeWordDetector` / `MockWakeWordDetector` | `REAL + PARTIAL` |
| **File Operations** | Static mock string returns | `FileTool` | `MOCK / FALLBACK ONLY` |
| **Browser Interaction** | Static mock string returns | `BrowserTool` | `MOCK / FALLBACK ONLY` |
| **REST API HTTP** | Static mock string returns | `APITool` | `MOCK / FALLBACK ONLY` |
| **Vision Detectors** | Mock person/object detectors | `MockPersonDetector` / `MockObjectDetector` | `MOCK / FALLBACK ONLY` |
| **Camera Hardware** | OpenCV mock wrappers | `MockCameraProvider` | `MOCK / FALLBACK ONLY` |
| **Robotics Hardware** | Mock motor/sensor controllers | `MockMotorController` / `MockSensorArray` | `MOCK / FALLBACK ONLY` |

---

## 5. Provider Inventory

1. **LLM Providers**:
   - `LLMProvider` (Abstract base interface)
   - `GeminiLLMProvider` (Real Google Gemini 2.5 Flash / Pro via `google-genai`)
   - `OpenAILLMProvider` (Real OpenAI / Groq REST client)
   - `MockLLMProvider` (Offline mock provider for deterministic testing)
   - Factory: `create_llm_provider()` in `aura.cognition.factory`

2. **Audio & Voice Providers**:
   - `STTProvider` / `FasterWhisperSTTProvider` / `MockSTTProvider`
   - `TTSProvider` / `EdgeTTSProvider` / `MockTTSProvider`
   - `AudioInputProvider` / `SoundDeviceInputProvider` / `MockAudioInputProvider`
   - `AudioOutputProvider` / `SoundDeviceOutputProvider` / `MockAudioOutputProvider`
   - `WakeWordDetector` / `WhisperWakeWordDetector` / `MockWakeWordDetector`

3. **Vision Providers**:
   - `CameraProvider` / `MockCameraProvider`
   - `PersonDetector` / `MockPersonDetector`
   - `ObjectDetector` / `MockObjectDetector`

4. **Robotics Providers**:
   - `MotorController` / `MockMotorController`
   - `SensorArray` / `MockSensorArray`

---

## 6. EventBus Audit

- `EventBus` (`src/aura/events/bus.py`):
  - Provides thread-safe, lock-protected event subscription (`subscribe`), unsubscription (`unsubscribe`), publication (`publish`), history tracking (`history`), and pause/resume mechanisms (`pause`, `resume`).
  - Supports event filtering functions (`EventFilter`) and global wildcards (`*`).
  - Currently used across modules (`AudioModule`, `AutonomyModule`, `CognitionModule`, `ToolsModule`).

### Architectural Finding:
Can AURA react to events without violating Stage 16 executive authority?
**YES.** An event published to `EventBus` MUST NEVER invoke a tool directly. The supported flow is:
`External/Internal Event` $\rightarrow$ `EventBus` subscriber $\rightarrow$ `ConversationalRuntime.process_turn` or `CognitiveTurnInterpretation` $\rightarrow$ `ToolRegistry.validate_parameters(...)` $\rightarrow$ `RuntimeOrchestrator.execute_closed_loop(...)` $\rightarrow$ Stage 10–15 Governance $\rightarrow$ Authoritative Execution.

---

## 7. Sensory/Hardware Audit

- **Audio Subsystem**:
  - `AudioModule` coordinates `AudioInputProvider`, `AudioOutputProvider`, `WakeWordDetector`, `STTProvider`, and `TTSProvider`.
  - When real hardware or libraries are missing, `AudioModule` gracefully falls back to mock implementations without crashing.
- **Vision Subsystem**:
  - `VisionModule` provides camera frame capture and person/object detection abstractions. Mocks are used when hardware is absent.
- **Robotics Subsystem**:
  - `RoboticsModule` provides motor control, obstacle detection, and navigation abstractions. Mocks are used when hardware is absent.

### Hardware Independence Rule:
Stage 22 MUST NOT require specialized physical hardware (webcams, robotic arms, GPUs). All capability additions MUST run 100% reliably on conventional PC hardware with offline mock fallbacks for CI/test environments.

---

## 8. Memory Audit

- **Conversational Memory**: `ConversationalMemory` backed by `SQLiteMemoryStore` records multi-turn conversation sessions (`conversational_turns`).
- **Episodic Memory**: `EpisodicMemory` stores episodic experience events.
- **Semantic Memory**: `SemanticMemory` provides entity and concept indexing.
- **Working Memory**: `WorkingMemory` manages short-term context tokens.
- **Goal Store**: `GoalManager` manages persistent goals (`pgoal_*`).

---

## 9. Proactivity / Background Execution Audit

- **Continuous Autonomy Runtime**: `ContinuousAutonomyRuntime` (`src/aura/cognition/scheduling/continuous_runtime.py`) runs a background loop executing scheduled goals.
- **Schedule Dispatcher**: `ScheduleDispatcher` (`src/aura/cognition/scheduling/dispatcher.py`) dispatches temporal cron/duration schedules.
- **Key Invariant**:
  - *Proactive Cognition* (detecting an environment trigger or scheduled event and proposing a goal) is distinct from *Autonomous Execution Authority*.
  - Proactive goals MUST pass through `RuntimeOrchestrator.execute_closed_loop(...)` and evaluate Stage 10 Governance and Stage 11 Policy before any tool execution occurs.

---

## 10. Authority & Trust Boundary Analysis

```
┌────────────────────────────────────────────────────────────────────────┐
│                        UNTRUSTED BOUNDARY                              │
│                                                                        │
│   [User Input]    [External HTTP Payload]   [Sensors/Events]  [LLM]   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Untrusted Data
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        VALIDATION BOUNDARY                             │
│                                                                        │
│                  [ToolRegistry.validate_parameters]                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Validated Proposal
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    AUTHORIZED EXECUTIVE BOUNDARY                       │
│                                                                        │
│            [Stage 16 RuntimeOrchestrator.execute_closed_loop]          │
│                                   │                                    │
│   ┌───────────────────────────────┼───────────────────────────────┐    │
│   ▼                               ▼                               ▼    │
│ Stage 11: Policy        Stage 10: Governance            Stage 12: Exec │
│   │                               │                               │    │
│   ▼                               ▼                               ▼    │
│ Stage 13: Experience    Stage 14: Adaptation            Stage 15: Assur│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Authoritative Execution Result
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        GROUNDED RESPONSE BOUNDARY                      │
│                                                                        │
│               [LLMProvider.generate_grounded_response]                 │
└────────────────────────────────────────────────────────────────────────┘
```

### Risk of Second Authority:
- Creating a new `AssistantManager` or `EnvironmentManager` that directly executes tools or bypasses `RuntimeOrchestrator` would break the safety invariants of AURA 1.6.
- **Mitigation**: Stage 22 will NOT create any new manager or coordinator class with execution capabilities. All environment interaction tools will be implemented strictly as `BaseTool` subclasses registered in `ToolRegistry`.

---

## 11. Current Architecture Gaps

1. **Mock Tool Over-Reliance**: Built-in tools like `FileTool`, `APITool`, `BrowserTool`, and `SystemStatusTool` return static mock strings rather than performing real sandboxed environment interactions.
2. **Missing Real System Observation**: AURA cannot observe real host OS metrics (CPU usage, memory allocation, disk space, active processes, network connectivity).
3. **Missing Controlled Information Retrieval**: AURA cannot execute real, safe HTTP GET/REST requests or extract text from web URLs to answer informational user queries.
4. **Disconnected Voice Pipeline**: Real speech STT/TTS providers exist in `aura.audio`, but are not integrated into `ConversationalRuntime` for audio-in/audio-out conversational turns.

---

## 12. Candidate Stage 22 Capabilities

| Candidate Capability | Pros | Cons | Recommendation |
| :--- | :--- | :--- | :--- |
| **Candidate 1: Physical Robotics & Camera Vision** | High visual appeal | Requires physical webcams, motor hardware, and GPU weights; fails on headless CI. | **REJECTED** |
| **Candidate 2: Unrestricted System Execution & Shell Tools** | Unlimited host power | Extremely high security risk (arbitrary command execution, prompt injection vulnerabilities). | **REJECTED** |
| **Candidate 3: Real Environment Interaction & System Observation Capability Layer** | 100% hardware independent, runs on any PC, fills real-world capability gap, highly testable, 0 new authorities. | Requires careful sandboxing and HTTP timeout/safety limits. | **RECOMMENDED FOR STAGE 22** |

---

## 13. Capability Comparison Matrix

| Criteria | Candidate 1 (Robotics/Vision) | Candidate 2 (Shell Tools) | Candidate 3 (Environment & Info Retrieval) |
| :--- | :---: | :---: | :---: |
| **Hardware Independence** | NO | YES | **YES** |
| **100% Offline CI Testable** | NO | YES | **YES** |
| **Zero New Authority Violation** | YES | NO | **YES** |
| **Prompt Injection Protection** | MEDIUM | LOW (High Risk) | **HIGH (Strict Sandboxing)** |
| **Real-World Value** | LOW (No hardware) | HIGH | **HIGH** |
| **Stage 10–16 Governance Compatibility** | YES | RISKY | **100% COMPATIBLE** |

---

## 14. Recommended Stage 22 Capability

**Stage 22: Real Environment Interaction & System Observation Capability Layer**

Stage 22 will implement:
1. **Real System Observation Tool (`RealSystemObservationTool`)**:
   - Inspects real host CPU utilization, RAM usage, disk partition space, OS platform details, active process counts, and network interface status using standard Python libraries (`psutil` / `platform` / `os`).
2. **Real Sandboxed File Tool (`RealSandboxedFileTool`)**:
   - Executes real file reading, writing, and directory listing strictly confined within a configurable workspace sandbox directory (`data/sandbox/` or configured path), preventing path traversal attacks (`../`).
3. **Real Information Retrieval Tool (`RealHTTPRetrievalTool`)**:
   - Executes safe HTTP GET requests to fetch web page content, REST API data, or plain text with strict timeouts, size limits, and header sanitization.
4. **Real Voice Pipeline Adapter (`ConversationalVoiceAdapter`)**:
   - Integrates speech input (`STTProvider`) and speech output (`TTSProvider`) cleanly into `ConversationalRuntime` turns while preserving text-based offline determinism.

---

## 15. Why This Capability Is the Correct Next Increment

1. **Fills the Largest Real-World Gap**: Moves AURA from returning static mock strings to interacting with real environment data (OS metrics, sandboxed files, web content, voice).
2. **Zero Executive Authority Expansion**: All 3 new tools are `BaseTool` subclasses registered in `ToolRegistry` and executed strictly via Stage 16 `RuntimeOrchestrator`.
3. **100% Hardware Independent**: Runs on standard Windows/Linux/macOS PCs without physical peripherals.
4. **100% Offline Testable**: Includes deterministic mock fallbacks for all network and voice operations.
5. **Backwards Compatible**: Preserves all Stage 10–21 contracts without breaking existing tests.

---

## 16. Risks & Mitigations

### Security & Safety Risks:
- *Risk*: Path traversal in file operations (`path=../../etc/passwd`).
  - *Mitigation*: Strict path resolution verifying `resolved_path.startswith(sandbox_root)`.
- *Risk*: SSRF / Arbitrary network abuse in HTTP retrieval.
  - *Mitigation*: Restrict protocols (`http`, `https`), enforce timeouts (5s), limit response size (1MB max), and apply Stage 11 Policy rules.
- *Risk*: Prompt injection from untrusted web page content.
  - *Mitigation*: Web content is treated as untrusted text input to the grounded response generator, never passed as executable tool parameters without Stage 16 Policy re-evaluation.

### Backward Compatibility Risks:
- *Risk*: Existing Stage 20/21 tests depending on mock tool names.
  - *Mitigation*: Retain `FileTool`, `APITool`, `BrowserTool` aliases or register new tools alongside existing builtins.

---

## 17. Production Readiness Impact

Stage 22 will elevate AURA 1.6 Production Readiness from:
- **Speech Input/Output**: `PARTIAL` $\rightarrow$ `PASS` (Real Audio Pipeline Adapter verified).
- **Environment & Information Retrieval**: `MOCK / FALLBACK ONLY` $\rightarrow$ `PASS` (Real OS observation, sandboxed files, HTTP retrieval verified).

---

## 18. Explicit Non-Goals for Stage 22

1. **NO Arbitrary Subprocess / Shell Execution Tool**: Will NOT allow unconstrained command-line shell execution (`cmd.exe` / `bash`) to eliminate system compromise risks.
2. **NO Physical Robotics Hardware Dependencies**: Will NOT require physical servos or robotic arms.
3. **NO Second Executive Coordinator**: Will NOT create any manager class outside Stage 16 `RuntimeOrchestrator`.
4. **NO Automatic Git Commit / Push**: Strictly forbidden per repository rules.

---

## 19. Architectural Decision Summary

- **Decision**: Proceed with **Stage 22: Real Environment Interaction & System Observation Capability Layer**.
- **Deliverable Artifacts**:
  - `docs/AURA-1.6-STAGE22-ARCHITECTURAL-AUDIT.md` (this audit)
  - `implementation_plan.md` (detailed multi-phase implementation plan)
