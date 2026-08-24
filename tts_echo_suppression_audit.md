# TTS ECHO SUPPRESSION & MUTEX AUDIT (`tts_echo_suppression_audit.md`)

**Execution Mode**: READ-ONLY FORENSIC ANALYSIS + ROOT CAUSE INVESTIGATION  
**Status**: CONFIRMED MISSING PROTECTION MECHANISMS  
**Date**: 2026-08-24  

---

## 1. EVALUATION OF ECHO SUPPRESSION MECHANISMS

We audited the codebase for 6 standard acoustic echo suppression and half-duplex protections:

| Protection Mechanism | Code Status | Code Location | Forensic Observation |
|---|---|---|---|
| **1. Microphone Mute During TTS** | **MISSING** | `src/aura/audio/microphone.py` | Audio input stream is not hardware/software muted while TTS plays. |
| **2. Half-Duplex Lock Window** | **INSUFFICIENT** | `src/aura/audio/autonomous_agent.py:L509-L518` | `_speech_lock` sets `_is_speaking = True` during `tts.speak()`, but releases lock after fixed 300ms sleep (`time.sleep(0.3)`). |
| **3. Post-TTS Cooldown Window** | **INSUFFICIENT** | `src/aura/audio/autonomous_agent.py:L515` | Fixed 300ms is shorter than room acoustic decay (500-1200ms) and soundcard output buffer flush. |
| **4. Playback Lock Guard** | **PRESENT (PARTIAL)** | `src/aura/audio/autonomous_agent.py:L138-L141` | Discards captured audio if `_is_speaking` is `True` *during* capture, but fails once `_is_speaking` becomes `False`. |
| **5. WebRTC Acoustic Echo Cancellation (AEC)** | **MISSING** | `src/aura/audio/microphone.py` | No DSP software AEC or WebRTC AEC sub-module integrated into audio input stream. |
| **6. Adaptive Threshold Adjustment** | **MISSING** | `src/aura/audio/microphone.py:L153` | VAD threshold is fixed at 120.0 instead of dynamically adapting to background speaker level. |

---

## 2. EXACT CODE LOCATIONS OF DEFECTIVE PROTECTIONS

### Location 1: `AutonomousVoiceAgent._speak()` ([`src/aura/audio/autonomous_agent.py:L507-L518`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/autonomous_agent.py#L507-L518))
```python
def _speak(self, text: str) -> None:
    with self._speech_lock:
        self._is_speaking = True
    try:
        self.tts.speak(text)
    finally:
        # DEFECT: Fixed 300ms sleep is insufficient for room echo decay & audio driver buffer flush
        time.sleep(0.3)
        with self._speech_lock:
            self._is_speaking = False
```

### Location 2: `AutonomousVoiceAgent.run()` ([`src/aura/audio/autonomous_agent.py:L121-L127`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/autonomous_agent.py#L121-L127))
```python
# DEFECT: Immediately calls record_until_silence() 0ms after _is_speaking becomes False
with self._speech_lock:
    currently_speaking = self._is_speaking
if currently_speaking:
    time.sleep(0.1)
    continue

audio_bytes = self.recorder.record_until_silence(...)
```

---

## 3. REQUIRED PROTECTION ARCHITECTURE (FOR FUTURE STAGE)

To eliminate voice loopbacks, the protection architecture must implement:
1. **Dynamic Post-TTS Cooldown**: Increase post-TTS cooldown guard from 300ms to **800ms–1000ms**.
2. **Minimum Speech Duration Threshold**: Require at least **4 consecutive speech chunks (400ms)** and minimum total speech duration >= 500ms before triggering STT.
3. **Transcript Self-Matching Guard**: Compare STT transcript against recent assistant response text. If similarity > 70%, discard turn as self-listening echo.
