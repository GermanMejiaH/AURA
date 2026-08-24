# USER-BEHAVIOR ROBUSTNESS AUDIT (`user_behavior_risk_audit.md`)

**Execution Mode**: FORENSIC REVIEW + PILOT DEPLOYMENT PLANNING  
**Status**: REVIEWED & BEHAVIORAL RISKS MITIGATED  
**Date**: 2026-08-24  

---

## 1. USER INTERACTION PATTERNS & RISKS

Real users interact unpredictably. We audited AURA 1.6 against 5 real-world user interaction risks:

### 1. Rapid-Fire / Overlapping Utterances
- **Behavior**: User speaks multiple sentences back-to-back without waiting for TTS completion.
- **Handling**: Speech Mutex Guard (`_speech_lock`) discards audio captured during active TTS playback unless user voice triggers barge-in. `interrupt_speaking()` terminates TTS output cleanly.

### 2. Malformed / Empty Inputs
- **Behavior**: STT produces 0-length text or non-speech noise tokens (`"..."`, `"[música]"`).
- **Handling**: `if not user_text: continue` filters empty transcripts instantly before cognitive cycle initiation (0 token cost).

### 3. Contradictory Statements
- **Behavior**: User says `"Tengo 26 años"` then `"Tengo 27 años"`.
- **Handling**: `SemanticMemory.add_fact()` updates facts by matching `(subject, predicate)` pairs, replacing outdated values with updated facts while maintaining single semantic source of truth.

### 4. Ambiguous / Vague Directives
- **Behavior**: User says `"Haz eso"` without specifying task context.
- **Handling**: `ReasoningEngine` inspects WorkingMemory conversation turns. If ambiguity persists, LLM prompts user for clarification (`action: "RESPOND"`).

### 5. Out-of-Scope Tool Requests
- **Behavior**: User asks AURA to perform an unsupported system action.
- **Handling**: Tool router finds 0 matching tools, falls back to conversational response without throwing errors.
