# SHUTDOWN ROOT CAUSE AUDIT (`shutdown_root_cause.md`)

**Execution Mode**: READ-ONLY FORENSIC ANALYSIS + ROOT CAUSE INVESTIGATION  
**Status**: ROOT CAUSE CONFIRMED  
**Date**: 2026-08-24  

---

## 1. AUDIT OBJECTIVE

Determine the exact technical sequence and code path that caused AURA to output:  
`"AURA: Desactivando modo autónomo continuo. Hasta luego."` and terminate continuous execution.

---

## 2. FORENSIC EVIDENCE & CODE TRACE

### Code Location 1: `ControlIntentDetector.is_exit()` ([`src/aura/cognition/intent.py:L148-L156`](file:///c:/Users/Andres/Desktop/AURA/src/aura/cognition/intent.py#L148-L156))

```python
for variant in cls.EXIT_VARIANTS:
    norm_variant = cls.normalize_text(variant)
    if filtered_norm == norm_variant or norm == norm_variant:
        return True
    # CRITICAL VULNERABILITY: Any utterance <= 3 words containing an exit variant returns True
    if len(filtered_words) <= 3 and norm_variant in filtered_norm:
        return True
```

- **Variants Monitored**: `"salir"`, `"salid"`, `"salida"`, `"exit"`, `"adios"`, `"adiós"`, `"chao"`, `"bye"`, `"cerrar"`, `"cierra"`, `"cierra la sesión"`, `"apágate"`, `"hasta luego"`, `"nos vemos"`, etc.
- **Flaw**: If STT transcribes background noise or ambient TV speech into a 1–3 word string containing any exit variant (e.g., `"chao"`, `"cierra"`, `"bye"`, `"salir"`), `is_exit()` unconditionally returns `True`.

### Code Location 2: Minimum Transcript Guard Bypass ([`src/aura/audio/autonomous_agent.py:L169-L173`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/autonomous_agent.py#L169-L173))

```python
is_exit_cmd = ControlIntentDetector.is_exit(user_text)
is_greeting_cmd = ControlIntentDetector.is_greeting(user_text)
# CRITICAL VULNERABILITY: If is_exit_cmd is True, short transcript filter (<10 chars) is bypassed!
if len(user_text.strip()) < 10 and not (is_exit_cmd or is_greeting_cmd):
    print(f"  🛑 [VOICE GUARD] Transcript rejected (too short: '{user_text}')")
    continue
```

- **Flaw**: A 4-character transcript like `"chao"` or `"bye"` bypasses the minimum length filter because `is_exit_cmd` is `True`.

### Code Location 3: Unconditional Loop Termination ([`src/aura/audio/autonomous_agent.py:L205-L214`](file:///c:/Users/Andres/Desktop/AURA/src/aura/audio/autonomous_agent.py#L205-L214))

```python
if ControlIntentDetector.is_exit(user_text):
    telemetry.increment("fastpath_exit_commands")
    telemetry.record_interaction(user_text, "EXIT")
    farewell = "Desactivando modo autónomo continuo. Hasta luego."
    print(f"\n[AURA]: {farewell}")
    self._speak(farewell)
    telemetry.record_latency("time_turn_ms", (time.perf_counter() - t_turn_start) * 1000)
    break  # CRITICAL: Immediately terminates continuous loop!
```

---

## 3. AUDIT FINDINGS SUMMARY

1. **Transcript that caused shutdown**: An ambient noise / TV / background speech fragment transcribed by FasterWhisper as a short 1–3 word phrase containing an exit variant (e.g. `"chao"`, `"bye"`, `"cierra"`, `"salir"`).
2. **Executed Code Path**: `stt.transcribe()` -> `ControlIntentDetector.is_exit()` (returns `True`) -> bypasses Voice Guard min length -> `AutonomousVoiceAgent._loop()` lines 205-214 -> `_speak(farewell)` -> `break`.
3. **Was there confirmation?**: **NO**. The system executes an unconfirmed, single-pass shutdown without requesting user confirmation (`"¿Estás seguro de que deseas salir?"`).
4. **Was it a false activation?**: **YES (CONFIRMED)**. The shutdown was triggered by an unvalidated false STT recognition of background ambient noise.
