# PAYLOAD INFLATION FORENSICS AUDIT (`payload_inflation_forensics.md`)

**Execution Mode**: READ-ONLY FORENSIC ANALYSIS + ROOT CAUSE INVESTIGATION  
**Status**: AUDIT COMPLETE  
**Date**: 2026-08-24  

---

## 1. AUDIT OBJECTIVE

Investigate the root cause of `HTTP 413 Request Entity Too Large` payload failures during field pilot continuous voice execution.

---

## 2. FORENSIC PAYLOAD PIPELINE ANALYSIS

```text
[CognitiveContextBuilder.build()] (src/aura/cognition/context.py:L262)
       │
       ├─► 1. System Instruction & Identity (~400 tokens)
       ├─► 2. Persistent Memories & CWM Entities (~300 tokens)
       ├─► 3. Episodic Experiences & Goal Manager (~600 tokens)
       ├─► 4. Untruncated Tool Results (1,000 to 8,000+ tokens)
       │      • System Status, File Outputs, CLI Tool Outputs appended raw
       ├─► 5. Adaptive Conversation History (Up to 12 turns = 24 messages)
       │      • History contains previous turns' large tool outputs (~2,000 to 5,000 tokens)
       │
       ▼
[to_system_prompt() + to_formatted_prompt()] (src/aura/cognition/context.py:L124 & L214)
       │  • Formats combined prompt string (e.g. 5,000 - 12,000 tokens)
       ▼
[OpenAILLMProvider.generate_response()] (src/aura/cognition/openai_provider.py:L56)
       │  • Provider Model: groq/compound
       │  • Injects ~1,979 extra server-side tokens (tool schemas, compound multi-agent rules)
       ▼
[Cloud Provider API Endpoint (Groq / OpenRouter)]
       │  • Request exceeds API endpoint max payload / token limit (e.g. 8,192 tokens or 128KB payload)
       └──────► RETURNS HTTP 413 REQUEST ENTITY TOO LARGE
```

---

## 3. AUDIT FINDINGS SUMMARY

1. **Component Inflating Payload**:
   - **Primary Component**: Untruncated `tool_results` in `to_system_prompt()` ([`src/aura/cognition/context.py:L203-L210`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/context.py#L203-L210)).
   - **Secondary Component**: Adaptive conversation history expanding up to 12 turns (`get_max_history_turns()` -> 24 dialogue messages) in [`src/aura/cognition/context.py:L225`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/context.py#L225).
   - **Tertiary Component**: Cloud provider model `groq/compound` adding ~1,979 tokens of server-side schemas.

2. **Payload Size Before Failure**:
   - Estimated raw prompt size before failure: **8,500 to 14,000 tokens** (~35KB - 58KB JSON payload).

3. **Provider Allowed Payload Limit**:
   - Free-tier / standard Groq and OpenRouter REST API endpoints enforce a max prompt limit of **8,192 tokens** or 128KB payload limits.

4. **Is the problem fixed or does it persist?**:
   - **PERSISTS (UNSOLVED IN CODE)**. While Stage 26.3F capped default history, adaptive history expansion (up to 12 turns) and raw untruncated tool outputs can still combine to trigger HTTP 413 errors on multi-tool turns.
