# LONG-RUN PILOT RISK ASSESSMENT (`long_run_risk_assessment.md`)

**Execution Mode**: READ-ONLY FORENSIC ANALYSIS + ROOT CAUSE INVESTIGATION  
**Status**: AUDIT COMPLETE  
**Date**: 2026-08-24  

---

## 1. RISK ASSESSMENT MATRIX (8-HOUR / 24-HOUR / 7-DAY CONTINUOUS OPERATION)

We evaluated 8 long-run operational risk categories for continuous pilot deployment:

| Risk Category | Severity | 8h Risk | 24h Risk | 7-Day Risk | Root Cause / Technical Description |
|---|---|---|---|---|---|
| **1. Accidental Shutdown** | **CRITICAL** | High | Certain | Guaranteed | Single-word false exit detection (`ControlIntentDetector.is_exit()`) without user confirmation kills process on ambient noise. |
| **2. VAD False Activations** | **CRITICAL** | High | Certain | Guaranteed | Static threshold (120.0) without noise floor tracking or ZCR/formant filter causes constant 85%+ ambient noise capture. |
| **3. Payload Inflation (HTTP 413)** | **HIGH** | Medium | High | Certain | Adaptive 12-turn history + untruncated tool outputs + `groq/compound` overhead triggers HTTP 413 on complex turns. |
| **4. Rate Limits (HTTP 429)** | **HIGH** | Medium | High | Certain | Continuous false VAD activations generate rapid LLM API calls, exceeding cloud provider RPM/TPM limits. |
| **5. SQLite Database Growth** | **MEDIUM** | Low | Medium | High | Unbounded event logging and telemetry snapshots inflate `aura.db` WAL log files over extended multi-day runs. |
| **6. Log File Disk Inflation** | **LOW** | Low | Low | Medium | Mitigated by Stage 27.0 `RotatingFileHandler` (10MB max, 5 backups), capping total logs at 50MB. |
| **7. Thread Leakage Growth** | **LOW** | Low | Low | Low | Verified in Stage 26.4 endurance audit (500 cycles completed with 0 thread leaks). |
| **8. Memory / RAM Leakage** | **LOW** | Low | Low | Low | Garbage collection handles turn objects cleanly; zero unbounded growth observed in long runs. |

---

## 2. DETAILED SEVERITY BREAKDOWN

### CRITICAL RISK 1: Accidental Process Shutdown
- **Impact**: In a multi-hour pilot run, ambient noise transcribed as `"chao"`, `"cierra"`, or `"salir"` immediately terminates `AutonomousVoiceAgent`. The system cannot survive continuous operation without process supervisor / interactive confirmation guard.

### CRITICAL RISK 2: Unbounded VAD False Activations & API Exhaustion
- **Impact**: Static VAD threshold (120.0) captures ambient noise continuously every few minutes, wasting thousands of API tokens and triggering rate limits (HTTP 429).

### HIGH RISK 1: HTTP 413 Payload Explosion
- **Impact**: Complex multi-tool or 12-turn history conversations cause HTTP 413 payload rejections, breaking conversation continuity.
