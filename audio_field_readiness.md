# REAL-WORLD AUDIO FIELD READINESS (`audio_field_readiness.md`)

**Execution Mode**: FORENSIC REVIEW + PILOT DEPLOYMENT PLANNING  
**Status**: REVIEWED & FIELD READINESS ASSESSED  
**Date**: 2026-08-24  

---

## 1. REAL-WORLD AUDIO ENVIRONMENT RISKS

Field deployment introduces hardware, network, and environmental variables absent in synthetic benchmarks:

| Field Condition | Potential Failure Mechanism | AURA Mitigation Strategy | Status |
|---|---|---|---|
| **Microphone Disconnect** | PyAudio device read failure | `AutonomousVoiceAgent.run()` captures PyAudio errors, sleeps 0.3s, retries initialization without process crash. | **HANDLED** |
| **Bluetooth Headset Disconnect** | Audio output channel loss during TTS | `_speak()` exception block catches audio device write failure, logs `voice_turn_failures`, retries next turn. | **HANDLED** |
| **Ambient Background Noise** | High energy VAD false triggers | VAD `energy_threshold=120.0` and `min_speech_duration_sec=0.4` filter low-level ambient chatter. FastPath IGNORE handles non-actionable speech. | **HANDLED** |
| **Whisper STT Degradation** | Phonetic transcription errors (`"Don De Vivo"`) | `ControlIntentDetector.normalize_text()` applies STT phonetic transformations (`"don de"` -> `"donde"`). | **HANDLED** |
| **Barge-In / User Interruption** | User speaks while AURA TTS is active | Speech mutex guard (`_speech_lock`) and `interrupt_speaking()` stop active TTS playback immediately. | **HANDLED** |

---

## 2. HARDWARE & DEVICE SELECTION GUIDELINES

1. **Recommended Microphone**: USB directional microphone or noise-canceling headset with hardware gain control.
2. **PyAudio Device Indexing**: Specify explicit `input_device` index in `AutonomousVoiceAgent(input_device=...)` or allow default OS audio input device.
3. **STT Model Selection**:
   - `base` model (CPU default): 150-250ms latency, high accuracy for Spanish.
   - `small` model (GPU optional): 100-180ms latency, enhanced accuracy for noisy environments.
