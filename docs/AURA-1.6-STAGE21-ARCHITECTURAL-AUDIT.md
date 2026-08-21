# AURA 1.6 — STAGE 21 ARCHITECTURAL AUDIT
## Real Cognitive Provider Integration & Natural Conversational Intelligence

**Date**: August 20, 2026  
**Stage**: Stage 21 — Real Cognitive Provider Integration  
**Status**: `PHASE 0 AUDIT COMPLETE`  

---

## 1. Current LLM & Cognition Architecture

AURA 1.6 contains an existing, extensible provider abstraction layer located in `src/aura/cognition/`:

1. **Base Interface**: [`LLMProvider`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/provider.py#L16-L34)
   - `generate_response(prompt: str, system_instruction: str = "", context: dict[str, Any] | None = None) -> LLMResponse`
   - `structured_reason(prompt: str, schema: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]`

2. **Concrete Providers**:
   - `GeminiLLMProvider` ([`src/aura/cognition/gemini_provider.py`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/gemini_provider.py)): Real integration with Google Gemini (`google.genai` SDK or `google.generativeai` legacy fallback). Supports `gemini-2.5-flash`.
   - `OpenAILLMProvider` ([`src/aura/cognition/openai_provider.py`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/openai_provider.py)): OpenAI-compatible REST API integration for Groq, OpenRouter, OpenAI (`gpt-4o-mini`), and local endpoints.
   - `RealLLMProvider` ([`src/aura/cognition/real_llm_provider.py`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/real_llm_provider.py)): REST client for local Ollama endpoints.
   - `MockLLMProvider` ([`src/aura/cognition/provider.py`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/provider.py#L36-L68)): Offline mock provider for deterministic CI/unit testing.

3. **Provider Factory**: `create_llm_provider(...)` ([`src/aura/cognition/factory.py`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/factory.py))
   - Auto-detects provider availability from environment variables (`AURA_LLM_PROVIDER`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_BASE_URL`) or `ConfigurationManager`.
   - Falls back gracefully to `MockLLMProvider` when no valid credentials or endpoints are available.

---

## 2. Existing Gemini Provider Analysis

- **Location**: [`src/aura/cognition/gemini_provider.py`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/gemini_provider.py)
- **SDK Support**: Modern `google.genai` Client (`Client(api_key=...)`) with fallback to legacy `google.generativeai`.
- **Credential Handling**:
  - Checks parameter `api_key`, then `os.environ.get("GEMINI_API_KEY")`, then `ConfigurationManager`.
  - Graceful Exception Catching: Distinguishes missing API key, unauthenticated OAuth tokens, invalid keys, resource exhaustion, and network errors without crashing the runtime.
- **Structured Output Support**:
  - `structured_reason(...)` sends a JSON system instruction and strips markdown backticks (` ```json `) to return a clean `dict`.

---

## 3. Existing Conversational Runtime Integration Points

In Stage 20, [`ConversationalRuntime`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/scheduling/conversational_runtime.py) operates as follows:
- `process_turn(...)`: Entry point receiving `conversation_id` and `user_input`.
- `_resolve_tool_proposal(...)`: Uses deterministic regex/pattern heuristics to formulate tool proposals (`calculator_tool`, `datetime_tool`, `system_status_tool`, `unsupported`, `ambiguous`).
- `_generate_natural_response(...)`: Uses string formatting templates based on tool outputs.

### Stage 21 Integration Strategy:
In Stage 21, `ConversationalRuntime` will accept an optional `llm_provider: LLMProvider | None = None`.
- When an active `LLMProvider` (such as `GeminiLLMProvider`) is available and credentialed, `ConversationalRuntime` delegates cognitive interpretation, tool proposal formulation, and grounded response synthesis to the provider via structured prompts.
- If credentials are absent or the LLM call fails/times out, `ConversationalRuntime` falls back cleanly to its Stage 20 deterministic rules, guaranteeing 100% test suite determinism and offline reliability.

---

## 4. Strongly Typed Cognitive Response Contract

To avoid fragile string parsing, Stage 21 introduces a typed cognitive contract:

```python
class CognitiveMode(Enum):
    DIRECT_RESPONSE = "direct_response"
    TOOL_PROPOSAL = "tool_proposal"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"
    PROVIDER_ERROR = "provider_error"

@dataclass(frozen=True)
class ToolCallProposal:
    tool_name: str
    arguments: dict[str, Any]

@dataclass(frozen=True)
class CognitiveTurnInterpretation:
    mode: CognitiveMode
    direct_response: str | None = None
    tool_proposal: ToolCallProposal | None = None
    reasoning: str | None = None
    confidence: float = 1.0
    error_message: str | None = None
```

---

## 5. Tool Proposal Validation & Safety Invariants

Before any proposed tool call reaches Stage 16 `RuntimeOrchestrator`:
1. **Tool Existence**: Verified against `ToolRegistry.get(tool_name)`. If non-existent (e.g. LLM proposes `"delete_all_files"`), proposal is rejected safely.
2. **Schema & Argument Validation**: Parameters validated via `ToolRegistry.validate_parameters(tool_name, **arguments)`. Unknown or mistyped arguments are rejected.
3. **No Direct Execution Path**: The LLM proposal object is **untrusted data**. It is converted into an internal Python action closure `action_fn` and submitted exclusively to `RuntimeOrchestrator.execute_closed_loop(...)`.
4. **Stage 16 Authority Boundary**: `RuntimeOrchestrator` remains the **sole executive authority**. All proposed tools must pass:
   - Stage 15 `AssuranceEngine` (`SAFE_MODE` quarantine check)
   - Stage 11 `PolicyEngine` (Priority & Policy rules)
   - Stage 10 `GovernanceEngine` (`AutonomyScope` check)
   - Stage 12 `ExecutionEngine` (Transactional execution)
   - Stage 13 `ExperienceEngine` (Outcome recording)
   - Stage 14 `AdaptationEngine` (HITL `APPROVED != APPLIED` invariant)

---

## 6. Grounded Response Generation

When a tool operation completes in Stage 16:
- The authoritative `RuntimeOperation` and raw return value (`tool_output`) are passed back to `ConversationalRuntime`.
- The LLM provider receives a grounded prompt containing the user input and the **exact, authoritative tool output**.
- If tool execution fails or was blocked by Policy/Governance/SafeMode, the LLM is provided with the explicit failure reason and cannot fabricate a successful result.

---

## 7. Architectural Gaps & Resolution

| Identified Gap | Proposed Resolution |
| :--- | :--- |
| `ConversationalRuntime` lacks direct LLM provider integration. | Inject `LLMProvider` into `ConversationalRuntime.__init__` with automatic factory resolution (`create_llm_provider()`). |
| Absence of strongly typed cognitive turn interpretation contract. | Define `CognitiveMode`, `ToolCallProposal`, and `CognitiveTurnInterpretation` dataclasses. |
| Tool proposals could potentially contain malformed or invalid arguments. | Enforce `ToolRegistry.validate_parameters(...)` before orchestrator submission. |
| Risk of prompt injection attempting to bypass Stage 16 or mutate policy. | LLM output is strictly sanitized and treated as untrusted proposal data; executive authority remains 100% in Stage 16. |
| Deterministic test suite breaking if Gemini credentials are not set. | CI tests use `MockLLMProvider` or deterministic test providers. Real Gemini smoke test runs conditionally (`pytest.mark.skipif`). |

---

## 8. Executive Authority & Rule Compliance Statement

- **Rule 1**: Stage 16 `RuntimeOrchestrator` remains the **sole executive authority**. No new orchestrators or execution managers are created.
- **Rule 2**: LLM has **zero executive authority**. It cannot call tools directly, mutate SQLite, modify runtime state, change autonomy scope, or alter policies.
- **Rule 3**: All tool proposals pass through `RuntimeOrchestrator` $\rightarrow$ Policy $\rightarrow$ Governance $\rightarrow$ Execution.
- **Rule 4 & 5**: Real `GeminiLLMProvider` integrated behind the `LLMProvider` abstraction.
- **Rule 6**: API keys managed safely via `GEMINI_API_KEY` / `ConfigurationManager`. CI test suite remains 100% offline and deterministic.
- **Rule 7**: Natural responses strictly grounded in real `ExecutionResult` outputs.

---

## 9. Next Steps

1. Create `implementation_plan.md`.
2. Wait for user review and approval before modifying production code.
