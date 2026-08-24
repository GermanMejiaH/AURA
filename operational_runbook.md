# OPERATIONAL RUNBOOK (`operational_runbook.md`)

**Execution Mode**: OPERATIONAL PROCEDURES & MAINTENANCE GUIDELINES  
**Target Environment**: Pilot 1-User Desktop Deployment  
**Date**: 2026-08-24  

---

## 1. STARTUP & SHUTDOWN PROCEDURES

### Normal Startup
```powershell
# 1. Activate Virtual Environment
.\.venv\Scripts\Activate.ps1

# 2. Verify Environment Variables
$env:OPENAI_API_KEY = "your-api-key-here"

# 3. Launch AURA Autonomous Agent
python -m aura.main --mode autonomous
```

### Clean Shutdown
- **Voice Command**: Say `"salir"`, `"adiós"`, or `"desactivar"`.
- **Keyboard Interrupt**: Press `Ctrl+C` in terminal. AURA handles SIGINT cleanly, releasing audio devices and closing SQLite database connections.

---

## 2. DATABASE MAINTENANCE & BACKUPS

- **Database Location**: `data/aura.db` (WAL Mode enabled).
- **Automated Backup Strategy**:
  Daily cron job or backup script executing SQLite online backup:
  ```powershell
  sqlite3 data/aura.db ".backup data/aura_backup_$(Get-Date -Format 'yyyyMMdd').db"
  ```
- **Integrity Verification**:
  ```powershell
  sqlite3 data/aura.db "PRAGMA quick_check;"
  ```

---

## 3. LOG ROTATION & CLEANUP

- Log file `aura.log` automatically rotates when reaching 10 MB, keeping 5 backup files (`aura.log.1`, `aura.log.2`, etc.).
- Retention policy: Automatically purged after 30 days.

---

## 4. TROUBLESHOOTING COMMON FIELD ISSUES

### Issue 1: Microphone Not Capturing Audio
- **Symptom**: Terminal displays `Esperando voz...` continuously without detecting speech.
- **Resolution**: Check system default microphone in Windows Audio Control Panel. Verify input volume > 50%. Pass explicit device index via `--input-device`.

### Issue 2: Provider Rate Limit (HTTP 429)
- **Symptom**: Logs display `429 Rate Limit Exceeded`.
- **Resolution**: FastPath handles memory and greeting queries with 0 LLM calls. If persistent, verify OpenAI tier usage limit.
