# PRODUCTION VOICE RISK REPORT (`production_voice_risk_report.md`)

**Execution Mode**: READ-ONLY FORENSIC ANALYSIS + ROOT CAUSE INVESTIGATION  
**Status**: RISK CLASSIFICATION & RECOMMENDATIONS  
**Date**: 2026-08-24  

---

## 1. PRODUCTION RISK SEVERITY MATRIX

We evaluated 4 operational voice risks discovered during forensic field log analysis:

| Risk Category | Risk Description | Severity | Probability | Operational Impact |
|---|---|---|---|---|
| **A) Self-Listening Loopback** | Microphone capturing TTS speaker output, causing AURA to talk to itself continuously. | **CRITICAL** | High | Unusable voice UX, continuous LLM API token consumption, infinite loop. |
| **B) False Wakeups** | Ambient noise bursts / room reflections exceeding RMS 120.0 for 200ms triggering capture. | **HIGH** | High | Spurious processing cycles, user annoyance, unnecessary background turns. |
| **C) Token Inflation** | `groq/compound` server-side model injecting ~1,970 extra tokens into API payload. | **MEDIUM** | High | Increased TPM usage and API costs on cloud provider calls. |
| **D) Continuous Autonomous Loops** | Absence of transcript self-matching guard allowing self-talk to repeat endlessly. | **CRITICAL** | High | Runaway loopback cycles requiring manual process kill. |

---

## 2. SUMMARY OF CONFIRMED VS REJECTED ROOT CAUSES

### Confirmed Root Causes
1. **Short Post-TTS Cooldown Guard**: 300ms sleep in `AutonomousVoiceAgent._speak()` is shorter than room acoustic reverberation decay.
2. **Oversensitive VAD Activation**: 2 consecutive 100ms chunks above RMS 120.0 trigger capture without minimum speech duration verification.
3. **STT `initial_prompt` Conditioning**: FasterWhisper decoder hallucinated continuation fragment `'de la asistente virtual en español.'` when processing faint speaker echo.
4. **Cloud Provider Compound Model Overhead**: Model `groq/compound` injects ~1,500 server-side prompt tokens.

### Rejected Root Causes
1. **Windows Stereo Mix / WASAPI Loopback Selection**: Input device was confirmed to be physical hardware microphone.
2. **SQLite Database Corruption**: Memory store integrity is 100% verified.
3. **Memory Retrieval Scoring Defect**: FastPath and semantic retrieval performed correctly on input.

---

## 3. PRODUCTION RISK SCORE & GO/NO-GO RECOMMENDATION

- **Production Readiness Score**: **45 / 100** (Degraded due to Critical Self-Listening Loopback Risk)
- **Go / No-Go Recommendation**: **NO-GO FOR VOICE PILOT UNTIL STAGE 27.2 LOOPBACK FIX IS IMPLEMENTED**
- **Recommended Next Stage**: **STAGE 27.2 — VOICE LOOPBACK & ECHO HARDENING**
