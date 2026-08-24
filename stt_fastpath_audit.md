# STT VARIANT FASTPATH AUDIT (`stt_fastpath_audit.md`)

**Execution Mode**: IMPLEMENTATION + VALIDATION  
**Audit Target**: `ControlIntentDetector` Speech Normalization & FastPath Routing  
**Status**: PASSED  
**Date**: 2026-08-24  

---

## 1. DEFECT DESCRIPTION

- **Observed Behavior**: Speech-to-Text transcription variations like `"Don De Vivo"` or `"cuantos anios tengo"` failed regex matching in `ControlIntentDetector.DIRECT_MEMORY_PATTERNS`, triggering FastPath bypass and HTTP 413 errors.
- **Root Cause**:
  1. Whisper STT transcribes Spanish spoken phrase `"¿Dónde vivo?"` as `"Don de vivo"`.
  2. `normalize_text()` collapsed spaces but did not combine STT word splits (`"don de"` -> `"donde"`).
  3. STT substitute spellings (`"anios"` for `"años"`, `"kien"` for `"quien"`) were unhandled.

---

## 2. STT PHONETIC NORMALIZATION IMPLEMENTATION

Added STT normalization rules in [`src/aura/cognition/intent.py`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/intent.py#L115-L130):

```python
# STT Whisper phonetic normalization rules
norm = re.sub(r"\bdon\s+de\b", "donde", norm)
norm = re.sub(r"\banios\b", "anos", norm)
norm = re.sub(r"\bkien\b", "quien", norm)
norm = re.sub(r"\bsoi\b", "soy", norm)
norm = re.sub(r"\byamo\b", "llamo", norm)
```

---

## 3. VERIFICATION MATRIX FOR STT VARIANTS

| Raw STT Recognized Input | Normalized Text | FastPath Intercept | Action |
|---|---|---|---|
| `"Don De Vivo"` | `"donde vivo"` | **True** | FastPath (`"Vives en Medellín."`) |
| `"don de vivo"` | `"donde vivo"` | **True** | FastPath (`"Vives en Medellín."`) |
| `"¿Dónde vivo?"` | `"dónde vivo"` | **True** | FastPath (`"Vives en Medellín."`) |
| `"cuantos anios tengo"` | `"cuantos anos tengo"` | **True** | FastPath (`"Tienes 26 años."`) |
| `"¿Qué estudié?"` | `"qué estudié"` | **True** | FastPath (`"Tu actividad es ingeniería de software."`) |
| `"Donde trabajo"` | `"donde trabajo"` | **True** | FastPath (`"Trabajas como desarrollador."`) |
