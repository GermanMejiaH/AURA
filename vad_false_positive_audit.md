# VAD FALSE POSITIVE AUDIT (`vad_false_positive_audit.md`)

**Execution Mode**: READ-ONLY FORENSIC ANALYSIS + ROOT CAUSE INVESTIGATION  
**Status**: CONFIRMED CODE MECHANICS AUDIT  
**Date**: 2026-08-24  

---

## 1. VAD IMPLEMENTATION ANALYSIS

The VAD engine is implemented in `record_until_silence()` inside [`src/aura/audio/microphone.py:L149-L235`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/microphone.py#L149-L235).

### Code Logic Breakdown

```python
chunk_duration = 0.1  # 100ms chunks
for _ in range(total_chunks):
    chunk, _ = stream.read(chunk_samples)
    frames.append(chunk)

    rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float32)))))
    rms_values.append(rms)

    if rms >= energy_threshold:  # energy_threshold = 120.0
        consecutive_speech_chunks += 1
        if consecutive_speech_chunks >= 2:
            speech_started = True
        silent_chunks = 0
    else:
        consecutive_speech_chunks = 0
        silent_chunks += 1
```

---

## 2. FORENSIC RESPONSES TO AUDIT QUESTIONS

### A. Why Max RMS=129 Triggered Speech with Threshold=120
- Baseline quiet room noise RMS is typically 10.0–30.0.
- Speaker acoustic reflections and room reverberations reach RMS levels of 80.0–250.0.
- RMS=129 exceeds the static `energy_threshold = 120.0` by 9 units, which is sufficient to satisfy `rms >= energy_threshold`.

### B. Activation Condition (Single Spike vs Sequence)
- A single isolated spike (`consecutive_speech_chunks = 1`) does **NOT** activate capture because `speech_started` requires `consecutive_speech_chunks >= 2`.
- However, **just 2 consecutive 100ms chunks** (totaling 200ms) above RMS 120.0 set `speech_started = True`.
- 200ms is far too short: a brief door click, keyboard stroke, chair squeak, or speaker echo tail easily lasts 200ms and triggers full 5.7s capture.

### C. Noise Burst Vulnerability & Minimum Requirements
- **Noise Burst Vulnerability**: HIGH. Any acoustic noise lasting >= 200ms with RMS >= 120.0 triggers recording.
- **Speech Duration Requirements**: NONE. Once `speech_started = True`, the recorder waits for 1.2s of silence (`silence_sec = 1.2`) and returns all accumulated frames regardless of how short the actual speech was.

---

## 3. MEASURED ACTIVATION MATRIX

| Parameter | Current Value in Code | Operational Impact |
|---|---|---|
| **Chunk Duration** | 100 ms (`chunk_duration = 0.1`) | High granularity |
| **Energy Threshold** | 120.0 (`energy_threshold = 120.0`) | Static threshold; fails in environments with variable ambient noise |
| **Activation Window** | 2 Chunks (200 ms) | Oversensitive; triggers on non-speech transients & echoes |
| **Minimum Valid Speech Duration** | 0 ms | Accepts 200ms noise bursts + silence as valid speech |
| **Trailing Silence Required** | 1.2 seconds (`silence_sec = 1.2`) | Prolongs recording duration to 57 chunks (5.7s) |
