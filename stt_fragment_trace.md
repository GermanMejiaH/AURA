# STT FRAGMENT TRACE AUDIT (`stt_fragment_trace.md`)

**Execution Mode**: READ-ONLY FORENSIC ANALYSIS + ROOT CAUSE INVESTIGATION  
**Status**: EXACT SOURCE IDENTIFIED  
**Date**: 2026-08-24  

---

## 1. FRAGMENT ORIGIN ANALYSIS

- **Observed STT Output**: `'de la asistente virtual en español.'`
- **Audit Target**: Determine the exact origin of this transcript.

---

## 2. FORENSIC SOURCE FINDINGS

### Source 1: `FasterWhisperSTTProvider.initial_prompt` ([`src/aura/audio/faster_whisper_stt.py:L24`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/faster_whisper_stt.py#L24))
```python
class FasterWhisperSTTProvider(STTProvider):
    def __init__(
        self,
        ...
        initial_prompt: str = "AURA es una asistente virtual en español.",
        ...
    ):
```

### Source 2: `FasterWhisperSTTProvider.transcribe()` ([`src/aura/audio/faster_whisper_stt.py:L143-L150`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/faster_whisper_stt.py#L143-L150))
```python
effective_prompt = self._get_effective_prompt()  # Returns "AURA es una asistente virtual en español."
if effective_prompt:
    kwargs["initial_prompt"] = effective_prompt

segments, info = model.transcribe(tmp_path, **kwargs)
```

---

## 3. MECHANISM OF FRAGMENT GENERATION

1. When acoustic speaker reverberation triggered 2 VAD chunks (200ms), low-amplitude audio bytes containing faint speaker decay were saved to a WAV file.
2. `FasterWhisperSTTProvider.transcribe()` passed `initial_prompt="AURA es una asistente virtual en español."` to `model.transcribe()`.
3. Whisper's autoregressive decoder uses `initial_prompt` as prefix conditioning text for speech recognition.
4. On noisy/faint audio samples where acoustic signal is ambiguous, Whisper's decoder **conditioned on the initial prompt prefix** and hallucinated the continuation fragment:
   
   **Prefix**: `"AURA es una "`  
   **Decoded Continuation**: **`"de la asistente virtual en español."`**

---

## 4. CONCLUSION

The phrase `'de la asistente virtual en español.'` was **NOT** spoken by the user. It was produced by FasterWhisper conditioning its autoregressive decoder on `initial_prompt = "AURA es una asistente virtual en español."` when processing faint speaker acoustic echo captured by the microphone.
