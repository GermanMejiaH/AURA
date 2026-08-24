# PILOT DEPLOYMENT PLAN (`pilot_deployment_plan.md`)

**Execution Mode**: PILOT STRATEGY & FIELD VALIDATION PROTOCOL  
**Target User**: 1-User Desktop Environment  
**Recommended Pilot Duration**: 14 Days  
**Date**: 2026-08-24  

---

## 1. PILOT PHASE STRUCTURE

### Phase 1: Initial Calibration (Days 1–3)
- Deploy AURA 1.6 on primary user workstation.
- Verify mic gain, VAD sensitivity, and speaker volumes in user's typical physical office environment.
- Validate baseline memory persistence for name, age, location, occupation, and preferences.

### Phase 2: Daily Continuous Operation (Days 4–10)
- User operates AURA autonomously throughout 8-hour workday.
- Validate voice memory recall, general assistance, scheduling reminders, and FastPath response speed.
- Track daily telemetry dumps (`telemetry.json`).

### Phase 3: Field Endurance & Stability Review (Days 11–14)
- Audit cumulative memory retention, token consumption, and SQLite database health.
- Evaluate incident logs, false STT triggers, and system latency distributions (p50, p95, p99).

---

## 2. INCIDENT REPORTING & MONITORING PROCESS

- **Daily Telemetry Export**: Run daily telemetry dump script at 18:00 to archive performance counters and latency metrics.
- **Incident Collection**: Any unexpected behavior (STT misheard, incorrect memory recall, unexpected silence) is flagged in an incident log sheet with time of occurrence.

---

## 3. ROLLBACK PLAN

In the event of a critical blocking failure during pilot:
1. Stop `python -m aura.main`.
2. Restore SQLite database from latest daily backup `data/aura_backup_YYYYMMDD.db`.
3. Fall back to previous stable release artifact if necessary.
