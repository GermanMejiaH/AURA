# VOICE GUARD ARCHITECTURE DESIGN (`voice_guard_design.md`)

**Execution Mode**: FORENSIC FIX + IMPLEMENTATION + VALIDATION  
**Status**: IMPLEMENTED & EMPIRICALLY VERIFIED  
**Date**: 2026-08-24  

---

## 1. ARCHITECTURE OVERVIEW & DEFENSE IN DEPTH

The Voice Guard protection layer prevents AURA from listening to its own TTS speaker output, false VAD noise triggers, and STT prompt hallucinations. It implements 5 concentric protection boundaries:

```text
[Audio Input Stream]
       │
       ▼
1. VAD Sustained Speech Filter (microphone.py)
   • Requires 5 consecutive 100ms chunks (500ms) with RMS >= 120.0
   • Filters short room reflections & noise bursts (< 500ms)
       │
       ▼
2. Post-TTS Cooldown Window (autonomous_agent.py)
   • Enforces POST_TTS_COOLDOWN_SEC = 2.0s sleep before clearing _is_speaking
   • Holds off microphone capture during acoustic room echo decay
       │
       ▼
3. Minimum Transcript Validation (autonomous_agent.py)
   • Rejects transcripts shorter than 10 characters (unless greeting/exit)
   • Prevents noise fragments ("mmm", "eh", "si") from triggering LLM
       │
       ▼
4. Self-Transcript Detector (autonomous_agent.py)
   • Compares user_text against last_tts_output via SequenceMatcher
   • Discards transcripts with similarity >= 70% or substring matches
       │
       ▼
5. Echo Window Protection (autonomous_agent.py)
   • Inspects captures within 2.0s after TTS finishes
   • Discards captures with similarity >= 50% or substring matches
       │
       ▼
[Cognition & LLM Pipeline] (Only clean, validated human speech passed)
```

---

## 2. CODE LOCATIONS OF IMPLEMENTED PROTECTIONS

1. **VAD Sustained Speech**: [`src/aura/audio/microphone.py:L220`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/microphone.py#L220) (`consecutive_speech_chunks >= 5`).
2. **Post-TTS Cooldown & Output Storage**: [`src/aura/audio/autonomous_agent.py:L48`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/autonomous_agent.py#L48) (`POST_TTS_COOLDOWN_SEC = 2.0`) & [`L514-L518`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/autonomous_agent.py#L514-L518) (`_speak()` storage and 2.0s sleep).
3. **Voice Guard Filters**: [`src/aura/audio/autonomous_agent.py:L166-L197`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/autonomous_agent.py#L166-L197) (Min length, self-transcript, echo window filters).
4. **Whisper Prompt Sanitization**: [`src/aura/audio/faster_whisper_stt.py:L24`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/faster_whisper_stt.py#L24) (`initial_prompt = ""`).
