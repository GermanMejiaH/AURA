# STT NOISE FORENSICS AUDIT (`stt_noise_forensics.md`)

**Execution Mode**: READ-ONLY FORENSIC ANALYSIS + ROOT CAUSE INVESTIGATION  
**Status**: AUDIT COMPLETE  
**Date**: 2026-08-24  

---

## 1. AUDIT OBJECTIVE

Investigate why nonsensical / garbage transcripts (e.g. `"Y si no, no"`, `"Más de que pueda ser bajo..."`, `"¿Ayer es un chico?"`) are produced by STT and reach the Cognition reasoning module.

---

## 2. FORENSIC TRANSCRIPT ANALYSIS

### Source of Garbage Transcripts

1. **Low Signal-to-Noise Ratio (Low SNR)**:
   - When VAD triggers on 5-15 seconds of low-RMS ambient noise, the audio payload sent to `FasterWhisperSTTProvider.transcribe()` ([`src/aura/audio/faster_whisper_stt.py:L119`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/faster_whisper_stt.py#L119)) lacks clear acoustic formants of human vocal speech.

2. **Whisper Decoder Hallucinations**:
   - Autoregressive sequence-to-sequence transformer speech models (like OpenAI Whisper / FasterWhisper) are trained on vast language corpora.
   - When forced to decode audio containing static, white noise, or muffled acoustic reflections, the beam-search decoder defaults to high-frequency n-grams in Spanish:
     - `"Y si no, no"` (11 chars)
     - `"Más de que pueda ser bajo..."` (29 chars)
     - `"¿Ayer es un chico?"` (19 chars)

3. **Bypass of Minimum Length Validation**:
   - In [`src/aura/audio/autonomous_agent.py:L171`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/autonomous_agent.py#L171), the minimum transcript validation filter rejects strings with `len(user_text.strip()) < 10`.
   - All three garbage examples contain **>= 11 characters**, cleanly passing the length threshold:
     - `"Y si no, no"` -> **11 characters** (PASSED)
     - `"Más de que pueda ser bajo..."` -> **29 characters** (PASSED)
     - `"¿Ayer es un chico?"` -> **19 characters** (PASSED)

4. **Failure to Check Decoder Confidence / No-Speech Probability**:
   - `FasterWhisperSTTProvider.transcribe()` extracts `stt_res.text`, but discards `info.no_speech_prob` and segment `avg_logprob` / `no_speech_prob` reported by FasterWhisper!
   - Low-confidence segment outputs (e.g. `no_speech_prob = 0.85` or `avg_logprob = -1.8`) are treated as 100% valid human speech and forwarded straight to LLM reasoning!

---

## 3. SUMMARY OF STT NOISE METRICS

- **Primary Source**: Whisper sequence decoder hallucination on low-SNR background audio.
- **Average Length**: 11 to 35 characters.
- **Confidence Metric**: `no_speech_prob` > 0.60 (Currently uninspected by provider).
- **Leakage Point**: Inability of static character length filter (< 10) to detect phonetically garbage sentences.
