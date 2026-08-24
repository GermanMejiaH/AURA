# VOICE LOOPBACK AUDIT (`voice_loopback_audit.md`)

**Execution Mode**: READ-ONLY FORENSIC ANALYSIS + ROOT CAUSE INVESTIGATION  
**Status**: CONFIRMED FORENSIC ROOT CAUSE  
**Date**: 2026-08-24  

---

## 1. EXECUTIVE SUMMARY

Production field logs exposed an autonomous loopback anomaly where AURA activated and responded when the user was silent:

```text
[AUTO VAD] Speech detected! Chunks=57
[Voz Detectada]: 'de la asistente virtual en español.'
[AURA]: AURA es una asistente virtual en español diseñada para ayudar...
```

Forensic investigation confirmed that AURA is capturing its own TTS audio playback from the physical room speakers or soundcard tail buffer, feeding self-generated audio into the microphone stream, transcribing it via Whisper STT, and initiating an endless self-listening loop.

---

## 2. COMPLETE AUDIO PIPELINE TRACE

The full audio pipeline flow was traced across the following code paths:

```text
[Microphone] 
    │
    ▼
[AudioRecorder.record_until_silence()] (src/aura/audio/microphone.py:L149)
    │  • Reads sounddevice.InputStream(dtype="int16") in 100ms chunks
    │  • Calculates RMS energy per chunk
    ▼
[VAD Threshold Logic] (src/aura/audio/microphone.py:L218-L222)
    │  • Captures speaker acoustic echo from physical room air / soundcard tail buffer
    │  • RMS = 129 exceeds energy_threshold = 120.0 for 2 consecutive chunks (200ms)
    │  • Sets speech_started = True
    ▼
[Audio Processing & Resampling] (src/aura/audio/microphone.py:L257-L276)
    │  • Concatenates 57 chunks (5.7 seconds of recorded audio)
    │  • Normalizes gain & writes WAV bytes
    ▼
[FasterWhisperSTTProvider.transcribe()] (src/aura/audio/faster_whisper_stt.py:L119)
    │  • Receives faint acoustic speaker echo audio
    │  • Conditions decoding on initial_prompt = "AURA es una asistente virtual en español."
    │  • Transcribes: "'de la asistente virtual en español.'"
    ▼
[CognitionModule.process_cognitive_cycle()] (src/aura/cognition/module.py:L453)
    │  • Treats self-captured audio transcript as user voice input
    ▼
[OpenAILLMProvider.generate_response()] (src/aura/cognition/openai_provider.py:L86)
    │  • Generates response: "AURA es una asistente virtual en español diseñada para ayudar..."
    ▼
[AutonomousVoiceAgent._speak()] (src/aura/audio/autonomous_agent.py:L507)
    │  • Sets _is_speaking = True
    │  • Plays TTS output audio through physical speakers
    │  • In finally: sleeps 300ms, sets _is_speaking = False
    │  • IMMEDIATELY re-enters run() loop and opens microphone InputStream (0ms delay)
    └──────► RE-ENTERS MICROPHONE CAPTURE (LOOPBACK REPEAT)
```

---

## 3. CONFIRMED ENTRY POINTS FOR SELF-GENERATED AUDIO

1. **Physical Acoustic Room Air Path**: Speaker playback sound waves reflect off room walls and enter the physical microphone capsule.
2. **Soundcard Driver Tail Buffer**: Operating system audio buffer (DirectSound / WASAPI / ALSA) retains audio samples during TTS playback termination.
3. **Premature `_is_speaking` Unlocking**: `_speak()` in [`src/aura/audio/autonomous_agent.py:L515`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/autonomous_agent.py#L515) sleeps for only 300ms before setting `_is_speaking = False`, which is shorter than acoustic room decay time (typically 500ms–1200ms) and hardware playback latency.
4. **Absence of Acoustic Echo Cancellation (AEC)**: Neither PyAudio, `sounddevice`, nor `AudioRecorder` implement hardware or software AEC filters.

---

## 4. ROOT CAUSE CONFIRMATIONS & REJECTIONS

- **CONFIRMED**: Acoustic speaker playback entering microphone input stream.
- **CONFIRMED**: Post-TTS cooldown period (300ms) is too short for room acoustic reverberation.
- **CONFIRMED**: STT `initial_prompt` conditioning hallucinated completion on muffled speaker tail.
- **REJECTED**: Windows Stereo Mix / WASAPI loopback device selection (Input device was physical mic).
- **REJECTED**: Memory corruption or SQLite database leak.
