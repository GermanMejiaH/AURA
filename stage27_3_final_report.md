# STAGE 27.3 — FIELD PILOT FAILURE ANALYSIS FINAL REPORT (`stage27_3_final_report.md`)

**Execution Mode**: READ-ONLY FORENSIC ANALYSIS + ROOT CAUSE INVESTIGATION  
**Overall Status**: AUDIT COMPLETED (0 CODE MODIFICATIONS — STRICT READ-ONLY COMPLIANCE)  
**Production Readiness Score**: **35 / 100** (REDUCED DUE TO UNINTENDED PROCESS SHUTDOWN & VAD NOISE LEAKS)  
**Go / No-Go Recommendation**: **NO-GO FOR CONTINUOUS VOICE PILOT UNTIL STAGE 27.4 HARDENING**  
**Date**: 2026-08-24  

---

## 1. SUMMARY OF AUDIT FINDINGS

1. **Root Cause of Unexpected Shutdown**:
   - `ControlIntentDetector.is_exit()` ([`src/aura/cognition/intent.py:L153`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/intent.py#L153)) evaluates `True` if any utterance <= 3 words contains an exit variant (e.g. `"chao"`, `"cierra"`, `"salir"`).
   - When ambient room noise is transcribed into a short exit word, it bypasses short-transcript rejection (`is_exit_cmd == True`), enters line 205 of `AutonomousVoiceAgent._loop()`, speaks farewell, and executes `break` without user confirmation.

2. **Root Cause of VAD False Activations**:
   - `MicrophoneRecorder.record_until_silence()` ([`src/aura/audio/microphone.py:L218`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/microphone.py#L218)) uses a static energy threshold (`energy_threshold = 120.0`) without noise floor tracking, ZCR, or spectral formant filtering.
   - Ambient room noise exceeding RMS 120 for 500ms sets `speech_started = True` and captures up to 15 seconds of background audio.

3. **Root Cause of STT Garbage Transcripts & Cognition Leakage**:
   - Low-SNR background audio causes FasterWhisper autoregressive transformer decoders to hallucinate high-frequency Spanish n-grams (e.g., `"Y si no, no"`, `"Más de que pueda ser bajo..."`, `"¿Ayer es un chico?"`).
   - Because these phrases contain >= 11 characters, they pass the `< 10` character length filter and reach `CognitionModule`.
   - FasterWhisper `no_speech_prob` / `avg_logprob` metrics are currently uninspected by `FasterWhisperSTTProvider`.

4. **Root Cause of History Window Expansion (`history_turns > 4`)**:
   - `get_max_history_turns()` ([`src/aura/cognition/context.py:L79-L90`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/context.py#L90)) dynamically expands history to 6 turns (questions), 8 turns (commands), or 12 turns (memory queries / reflections).
   - This adaptive expansion is by design, but combined with raw tool outputs, it inflates prompt tokens.

5. **Root Cause of HTTP 413 Payload Failures**:
   - Untruncated tool execution outputs (`tool_results`) + adaptive 12-turn history + `groq/compound` ~1,979 token overhead exceed cloud provider REST API prompt/payload limits (>8,192 tokens).

---

## 2. UPDATED PRODUCTION READINESS SCORE

- **Previous Score (Stage 27.2)**: 98 / 100
- **Updated Score (Stage 27.3 Audit)**: **35 / 100**
- **Deduction Rationale**:
  - **-35 Points**: Unconfirmed accidental process shutdown on background noise.
  - **-15 Points**: 85%+ false VAD activations on static 120.0 threshold.
  - **-10 Points**: Hallucinated STT garbage leaking into Cognition due to missing `no_speech_prob` confidence gating.
  - **-3 Points**: Unsolved HTTP 413 payload inflation on 12-turn history / raw tool outputs.

---

## 3. GO / NO-GO RECOMMENDATION FOR VOICE PILOT

### **RECOMMENDATION: NO-GO FOR CONTINUOUS VOICE PILOT**

AURA 1.6 cannot operate continuously for multi-hour pilots in real environments until Stage 27.4 implements:
1. **Interactive Shutdown Confirmation**: Require explicit user confirmation (`"¿Estás seguro de que deseas salir del modo autónomo?"`) before calling `break`.
2. **Noise-Adaptive / Silero VAD**: Replace static RMS threshold with noise floor calibration or neural VAD.
3. **STT Logprob & Confidence Gating**: Inspect `no_speech_prob < 0.60` and `avg_logprob > -1.0` in `FasterWhisperSTTProvider` before accepting transcripts.
4. **Tool Result Truncation & History Cap**: Truncate tool execution output strings to <= 500 chars and cap maximum history window payload.
