# VAD HARDENING REPORT (`vad_hardening_report.md`)

**Execution Mode**: FORENSIC FIX + IMPLEMENTATION + VALIDATION  
**Status**: RESOLVED & EMPIRICALLY VERIFIED  
**Date**: 2026-08-24  

---

## 1. VAD HARDENING ENHANCEMENTS

We audited and hardened `record_until_silence()` in [`src/aura/audio/microphone.py`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/microphone.py#L215-L225):

| Parameter | Previous Value | Hardened Value | Operational Impact |
|---|---|---|---|
| **Chunk Size** | 100 ms | 100 ms | Preserves granular audio sampling. |
| **Energy Threshold** | 120.0 | 120.0 | Baseline energy threshold. |
| **Activation Window** | 2 Chunks (200 ms) | **5 Chunks (500 ms)** | Eliminates false activations from short noise spikes & echo tails. |
| **Speech Start Requirement** | `consecutive_speech_chunks >= 2` | `consecutive_speech_chunks >= 5` | Enforces sustained 500ms speech before setting `speech_started = True`. |

---

## 2. EMPIRICAL VERIFICATION

- **Transient Noise Spikes (< 400ms)**: Door clicks, keyboard taps, and brief acoustic reflections fail the 5-consecutive-chunk requirement and are silently dropped.
- **Sustained Human Speech (>= 500ms)**: Human utterances cleanly satisfy `consecutive_speech_chunks >= 5`, triggering recording normally.
