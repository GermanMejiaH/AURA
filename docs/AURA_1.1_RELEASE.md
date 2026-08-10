# AURA 1.1 — DOCUMENTACIÓN TÉCNICA DEL RELEASE
## Plataforma de Agentes Autónomos Multi-Step Resilientes y Observables

---

## 1. Arquitectura General de AURA 1.1

AURA 1.1 amplía el motor reactivo de AURA 1.0 mediante una arquitectura agéntica modular de 5 etapas:

```text
                                 [ Usuario / CognitionModule ]
                                              │
                                              ▼
                                       [ AgentPlanner ]
                                              │
                                              ▼ (Persistencia previa)
                                      [ AgentPlanStore ] (SQLite)
                                              │
                                              ▼
┌────────────────────────────────────── [ AgentExecutor ] ──────────────────────────────────────┐
│                                             │                                                 │
│                        ┌────────────────────┴────────────────────┐                            │
│                        ▼                                         ▼                            │
│                 [ ToolRegistry ]                         [ TaskEvaluator ]                    │
│                        │                                         │                            │
│                        ▼                                   ├─ SUCCESS                         │
│                   [ BaseTool ]                             ├─ FAILED                          │
│                                                            └─ REPLAN_REQUIRED                 │
│                                                                  │                            │
│                                                                  ▼                            │
│                                                           [ AgentReplanner ] ─────────────────┤ (Recuperación)
└───────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
                                         [ EventBus ]
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
         [ AgentMetricsCollector ]                         [ AgentExecutionHistoryStore ]
       (Métricas & Seguridad en vivo)                      (Árboles de Ejecución en SQLite)
```

---

## 2. Componentes Principales

### **A. AgentPlanner (`src/aura/autonomy/planner.py`)**
- Traduce metas en lenguaje natural a modelos de dominio `AgentPlan` con tareas `AgentTask`.
- Valida determinísticamente las herramientas contra `ToolRegistry`.
- Elimina parámetros inseguros inyectados por el LLM (`_authorized`).
- Emite el evento `AgentPlanCreated`.

### **B. AgentPlanStore (`src/aura/memory/plan_store.py`)**
- Almacena de forma persistente e inmutable en SQLite los planes y tareas agénticas.
- Mantiene los estados de ejecución (`PENDING`, `IN_PROGRESS`, `SUCCESS`, `FAILED`, `WAITING_CONFIRMATION`).
- Garantiza la recuperación completa del estado agéntico tras reinicios de la aplicación.

### **C. AgentExecutor (`src/aura/autonomy/executor.py`)**
- Autoridad exclusiva para ejecutar tareas agénticas.
- Evalúa riesgos de seguridad (`requires_confirmation=True` o `risk_level="destructive"`) deteniendo la ejecución con el estado `WAITING_CONFIRMATION`.
- Coordina el flujo de re-planificación y emite el evento `AgentPlanCompleted`.

### **D. TaskEvaluator (`src/aura/cognition/evaluator.py`)**
- Clasifica determinísticamente los resultados de ejecución en `SUCCESS`, `FAILED` o `REPLAN_REQUIRED` mediante patrones estrictos de descarte.

### **E. AgentReplanner (`src/aura/autonomy/replanner.py`)**
- Genera estrategias alternativas ante fallos recuperables.
- Limita re-planificaciones mediante `max_replans`.
- Previene loops infinitos comparando la propuesta contra la tarea fallida.
- Purga parámetros `_authorized` de forma incondicional.

### **F. AgentMetricsCollector (`src/aura/autonomy/metrics.py`)**
- Suscriptor del `EventBus` que agrega en tiempo real métricas de planificación, tareas, re-planificación, herramientas y seguridad.

### **G. AgentExecutionHistoryStore (`src/aura/autonomy/history.py`)**
- Registra el historial cronológico e inalterable de ejecuciones en la tabla SQLite `agent_execution_history`.
- Proporciona el método `get_plan_execution_tree(plan_id)` para reconstruir la secuencia completa de ejecución.

---

## 3. Seguridad y Fronteras Deterministas

1. **Sin ejecución en LLM/Planners**: `AgentPlanner` y `AgentReplanner` únicamente proponen planes; jamás ejecutan herramientas.
2. **Sin comandos peligrosos**: No se utilizan `eval()`, `exec()` ni `subprocess`.
3. **Purga de `_authorized`**: Se elimina cualquier intento del LLM de inyectar autorización implícita.
4. **Validación estricta en `ToolRegistry`**: Las herramientas no registradas o parámetros inválidos son rechazados inmediatamente.
5. **Persistencia antes de ejecución**: Todo paso re-planificado se persiste en SQLite antes de su ejecución.

---

## 4. Comandos de Validación y Calidad

- **Análisis Estático (Linter)**:
  ```powershell
  .\.venv\Scripts\ruff check src tests scratch
  ```
- **Verificación de Tipos**:
  ```powershell
  .\.venv\Scripts\mypy src/aura
  ```
- **Suite de Pruebas**:
  ```powershell
  .\.venv\Scripts\pytest
  ```
