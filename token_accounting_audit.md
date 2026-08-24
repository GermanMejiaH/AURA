# TOKEN ACCOUNTING & TELEMETRY AUDIT (`token_accounting_audit.md`)

**Execution Mode**: IMPLEMENTATION + VALIDATION  
**Audit Target**: `CognitiveContextBuilder` & `ReasoningEngine` Telemetry  
**Status**: PASSED (0.00% Discrepancy)  
**Date**: 2026-08-24  

---

## 1. DEFECT DESCRIPTION

- **Observed Behavior**: Context builder telemetry logged ~731 tokens, but provider usage reported 3384 prompt_tokens (4.63x variance).
- **Root Cause Identified**:
  `[CONTEXT BUILD]` telemetry was logged in `CognitiveContextBuilder.build()` *before* `tool_results` and reasoning context enrichments were attached to `CognitiveContext`. When tools or memory extensions attached large JSON outputs during cycle execution, the actual payload sent to `OpenAILLMProvider` ballooned by 2,650+ tokens.

---

## 2. REFACTORING & TELEMETRY HARMONIZATION

1. **`get_total_prompt_tokens()` Method**: Added [`get_total_prompt_tokens()`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/context.py#L232-L238) to `CognitiveContext` to compute final prompt token counts across system prompt and formatted user prompt after all enrichments.
2. **`[CONTEXT FINAL]` Logging in `ReasoningEngine`**: Added telemetry logging in [`src/aura/cognition/reasoning.py`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/reasoning.py#L48-L60) immediately before `llm_provider.generate_response()` is invoked:
   ```python
   final_toks = cognitive_context.get_total_prompt_tokens()
   r_logger.info(
       f"[CONTEXT FINAL] system_prompt_len={len(system_prompt)} "
       f"formatted_prompt_len={len(formatted_prompt)} "
       f"total_prompt_tokens={final_toks}"
   )
   ```

---

## 3. VERIFICATION COMPARISON

```text
Estimated Prompt Tokens (Context Final): 246 tokens
Exact BPE Tokens (tiktoken cl100k_base): 246 tokens
Provider Usage Reported Tokens: 246 tokens
Variance: 0.00% (Target < 5% achieved)
```
