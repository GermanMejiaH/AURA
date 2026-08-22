# AURA 1.6 — STAGE 24 MIGRATION TRACEABILITY MATRIX

## 1. Traceability Overview
This document maps Stage 24 persistence integrity requirements to test scenarios, implementation modules, and schema migration steps.

---

## 2. Requirement to Code & Test Mapping

| Req ID | Requirement Description | Implementation Module | Test Scenario | Status |
| :--- | :--- | :--- | :--- | :---: |
| **REQ-24-01** | `PRAGMA user_version` migration engine | `src/aura/memory/store.py` | `test_sqlite_migration_from_legacy_v0_schema` | **VERIFIED** |
| **REQ-24-02** | Physical database backup & SHA-256 verification | `src/aura/memory/backup.py` | `test_stage24_real_database_fact_and_episode_operations` | **VERIFIED** |
| **REQ-24-03** | `facts.object_val` $\rightarrow$ `facts.object` column rename | `src/aura/memory/store.py` | `test_sqlite_migration_from_legacy_v0_schema` | **VERIFIED** |
| **REQ-24-04** | `episodes.event_type` and `payload` addition | `src/aura/memory/store.py` | `test_sqlite_migration_from_legacy_v0_schema` | **VERIFIED** |
| **REQ-24-05** | Deterministic legacy `details`/`tags` $\rightarrow$ `payload` JSON migration | `src/aura/memory/store.py` | `test_sqlite_migration_from_legacy_v0_schema` | **VERIFIED** |
| **REQ-24-06** | 100% data preservation across legacy records | `src/aura/memory/store.py` | `test_migration_preserves_existing_data` | **VERIFIED** |
| **REQ-24-07** | Migration idempotency (no-op on version == 1) | `src/aura/memory/store.py` | `test_migration_is_idempotent` | **VERIFIED** |
| **REQ-24-08** | Atomic transaction rollback on failure | `src/aura/memory/store.py` | `test_migration_rollback_on_failure` | **VERIFIED** |
| **REQ-24-09** | Current DDL schema integrity verification | `src/aura/memory/store.py` | `test_current_schema_integrity` | **VERIFIED** |
| **REQ-24-10** | Real database `data/aura.db` schema & data integrity | `src/aura/memory/store.py` | `test_real_database_schema_integrity` | **VERIFIED** |
| **REQ-24-11** | Real CLI fact addition & retrieval (`memory add/get`) | `src/aura/memory/store.py` | `test_stage24_real_database_fact_and_episode_operations` | **VERIFIED** |
| **REQ-24-12** | Real episode recording & payload retrieval | `src/aura/memory/store.py` | `test_stage24_real_database_fact_and_episode_operations` | **VERIFIED** |
| **REQ-24-13** | Process restart persistence simulation | `src/aura/memory/store.py` | `test_stage24_real_database_persistence_across_restart` | **VERIFIED** |
| **REQ-24-14** | Multi-turn `ConversationalRuntime` persistent memory integration | `src/aura/cognition/scheduling/conversational_runtime.py` | `test_stage24_conversational_runtime_memory_integration` | **VERIFIED** |
