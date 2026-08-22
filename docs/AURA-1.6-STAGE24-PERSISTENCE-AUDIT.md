# AURA 1.6 — STAGE 24 PERSISTENCE AUDIT & SCHEMA DRIFT REPORT

## 1. Context & Executive Summary
During manual CLI testing following Stage 23 certification, schema inconsistencies were discovered in the production database `data/aura.db`. Although automated integration tests passed against ephemeral test databases, the real persistent database `data/aura.db` failed on `facts` and `episodes` operations due to unmigrated historical schema changes.

This document presents the **Phase 0 Forensic Audit** detailing the expected schema, the real schema on disk in `data/aura.db`, the field-by-field differences, the data inventory to preserve, the migration strategy, risk assessment, and rollback plan.

---

## 2. Expected vs. Real Database Schemas

### 2.1 Table `facts`

#### Expected Schema (`src/aura/memory/store.py` & `src/aura/memory/models.py`)
```sql
CREATE TABLE facts (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
)
```

#### Real Schema on Disk (`data/aura.db`)
```sql
CREATE TABLE facts (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_val TEXT NOT NULL,  -- Legacy column name!
    confidence REAL NOT NULL DEFAULT 1.0,
    source TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL
)
```

#### Field-by-Field Mismatch
- Column on disk is named `object_val`, whereas code executes `INSERT INTO facts (... object ...)` and queries `row["object"]`.
- **Runtime Error**: `sqlite3.OperationalError: table facts has no column named object` on insert, and `KeyError: 'object'` ("No item with that key") on retrieval.

---

### 2.2 Table `episodes`

#### Expected Schema (`src/aura/memory/store.py`)
```sql
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'episode',
    summary TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    importance REAL NOT NULL DEFAULT 1.0
)
```

#### Real Schema on Disk (`data/aura.db`)
```sql
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    importance REAL NOT NULL DEFAULT 1.0
)
```

#### Field-by-Field Mismatch
- Columns `event_type` and `payload` are **MISSING on disk**.
- Columns `details` and `tags` are **PRESENT on disk (legacy format)**, whereas current Python code expects `details` and `tags` encoded inside a JSON string column named `payload`.
- **Runtime Error**: `sqlite3.OperationalError: table episodes has no column named event_type` on insert, and `KeyError: 'payload'` ("No item with that key") on retrieval.

---

### 2.3 Other Tables Status in `data/aura.db`

| Table Name | Disk Schema | Expected Code Schema | Match Status |
| :--- | :--- | :--- | :---: |
| `preferences` | `key, value, category, updated_at` | `key, value, category, updated_at` | **MATCH** |
| `memory_sessions` | `session_id, user_id, title, created_at, updated_at` | `session_id, user_id, title, created_at, updated_at` | **MATCH** |
| `conversation_turns` | `turn_id, session_id, role, content, intent_type, timestamp, metadata_json` | `turn_id, session_id, role, content, intent_type, timestamp, metadata_json` | **MATCH** |
| `agent_plans` | `plan_id, goal_id, goal_description, status, created_at, updated_at, replan_count, max_replans` | 8 columns | **MATCH** |
| `agent_tasks` | `task_id, plan_id, task_order, description, status, tool_name, parameters_json, result_json, error` | 9 columns | **MATCH** |
| `proactive_tasks` | 20 columns | 20 columns | **MATCH** |
| `proactive_task_executions` | 7 columns | 7 columns | **MATCH** |
| `proactive_notifications` | 10 columns | 10 columns | **MATCH** |

---

## 3. Preserved Data Inventory

The real database `data/aura.db` contains active historical user data that **MUST BE 100% PRESERVED**:

| Table Name | Preserved Record Count | Data Details & Sample Content |
| :--- | :---: | :--- |
| `facts` | **2 records** | `("b495...", "usuario", "color_favorito", "el rojo", 1.0, "user", ...)`<br>`("2555...", "usuario", "comida_favorita", "la pasta", 1.0, "user", ...)` |
| `episodes` | **263 records** | Historical interaction episodes (e.g., `"Usuario dijo: '¿Cuál es el estado del sistema?'"`) |
| `preferences` | **2 records** | `color_favorito` $\rightarrow$ `el rojo`, `comida_favorita` $\rightarrow$ `la pasta` |
| `memory_sessions` | **44 records** | Active and past conversational session headers |
| `conversation_turns` | **1658 records** | Recorded multi-turn dialogue logs with correlation IDs |
| `proactive_tasks` | **0 records** | Ready for Stage 23 proactive task initialization |
| `proactive_task_executions`| **0 records** | Ready for Stage 23 proactive execution logs |
| `proactive_notifications` | **0 records** | Ready for Stage 23 proactive notification logs |

---

## 4. Migration Strategy (V0 $\rightarrow$ V1)

### 4.1 Versioning Mechanism
- Use `PRAGMA user_version` inside `SQLiteMemoryStore`.
- Current DB `data/aura.db` has `PRAGMA user_version = 0`.
- Target schema version is `PRAGMA user_version = 1`.

### 4.2 Migration Execution Steps (Inside Single Transaction `with conn:`)

#### Step 1: Migration of `facts` Table
Execute column rename from `object_val` to `object`:
```sql
ALTER TABLE facts RENAME COLUMN object_val TO object;
```
*(SQLite 3.25+ native column renaming preserves all primary keys, defaults, and 100% of row data without table drop/recreate).*

#### Step 2: Migration of `episodes` Table
Execute deterministic column additions and payload JSON migration:
```sql
ALTER TABLE episodes ADD COLUMN event_type TEXT NOT NULL DEFAULT 'episode';
ALTER TABLE episodes ADD COLUMN payload TEXT NOT NULL DEFAULT '{}';

UPDATE episodes
SET payload = json_object('details', details, 'tags', json(tags))
WHERE (payload = '{}' OR payload IS NULL) AND (details IS NOT NULL AND details != '');
```

#### Step 3: Upgrade Version Pragma
```sql
PRAGMA user_version = 1;
```

---

## 5. Risk Assessment & Rollback Plan

### 5.1 Identified Risks
1. **Interrupted Migration**: Power loss or process failure mid-migration could leave tables partially altered.
   - *Mitigation*: Wrap all migration DDL/DML inside a single Python SQLite connection transaction (`with conn:`). SQLite guarantees atomic commit or total rollback.
2. **Corrupted JSON Serialization**: Invalid legacy string tags causing `json(tags)` syntax error during update.
   - *Mitigation*: Use defensive SQL fallback `json_object('details', details, 'tags', json_array())` if JSON parsing fails.
3. **Unexpected File Lock**: Concurrent CLI processes accessing `data/aura.db`.
   - *Mitigation*: Acquire `threading.RLock()` in Python and verify exclusive lock during migration.

### 5.2 Physical Backup & Rollback Procedure
Before running migration on `data/aura.db`:
1. Create timestamped physical copy: `data/aura.db.bak_<YYYYMMDD_HHMMSS>`.
2. Compute and store SHA-256 checksum of `data/aura.db`.
3. If migration fails or data validation fails:
   - Close active SQLite connection.
   - Restore `data/aura.db` from physical backup file.
   - Verify SHA-256 checksum matches pre-migration baseline.
