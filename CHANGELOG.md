# CHANGELOG

## [0.9.0] - 2026-08-10

### Added - Context-Aware Cognition & Conversational Continuity
- **Conversation Context Layer**: Introduced `ConversationContext` to manage multi-turn conversational state, active topic, active task, task details, active entity, and resolved anaphora.
- **Deterministic Anaphora Resolver**: Added `AnaphoraResolver` to conservatively analyze anaphoric references (`"cuál"`, `"esa"`, `"la"`, `"él"`) without guessing. Emits explicit `is_ambiguous = True` when multiple candidates exist, prompting AURA to ask for clarification.
- **Deterministic Context Filtering**: Implemented `ConversationContextFilter` to score and extract at most 8 relevant turns per cognitive cycle while strictly maintaining original chronological order.
- **Session State Expansion**: Extended `SessionContext` with `task_detail` and `active_entity` fields, plus helper methods for topic and task management.
- **Cognitive Context Integration**: Integrated `ConversationContext` into `CognitiveContext` and `CognitiveContextBuilder.to_system_prompt()`, formatting `[REFERENCIA ACTIVA]` and `[CONTEXTO CONVERSACIONAL RELEVANTE]` blocks without artificial empty sections.
- **Preserved Architectural Integrity**: Maintained full compatibility with AURA 0.8 Tool Orchestration, SQLite persistent memory, and CWM.

### Maintained & Verified
- 100% backward compatibility with AURA 0.1 – 0.8.
- 254/254 automated tests passing cleanly.
- 0 Ruff lint errors and 0 Mypy type errors.

## [0.8.0] - 2026-08-10

### Added - Tool Use & Action Orchestration
- **Tool Contract Extension**: Extended `ToolMetadata` with `risk_level` (`"safe"`, `"reversible"`, `"destructive"`), `requires_confirmation` (boolean), and `read_only` (boolean).
- **Parameter Validation**: Added `ToolRegistry.validate_parameters()` for contract validation before tool execution.
- **Deterministic Built-in Tools**:
  - `DateTimeTool`: Real system date, time, day of week, and ISO timestamp.
  - `CalculatorTool`: Safe mathematical evaluation using strict AST node white-listing (0% `eval()`).
  - `SystemStatusTool`: Real-time AURA lifecycle, module health, and state inspection.
- **Tool Events**: Introduced `ToolRequested`, `ToolExecutionStarted`, and `ToolConfirmationRequired` events.
- **Cognitive Context Expansion**: Added `tool_results` to `CognitiveContext` and formatted `[RESULTADOS DE HERRAMIENTAS RECIENTES]` block in system prompt.
- **ToolOrchestrator**: Implemented cognition-level tool orchestration with hybrid routing, safety/confirmation checks, and a hard limit of `max_tool_calls_per_turn = 3`.
- **Safety Policy**: Destructive or confirmation-required tools block automatic execution and publish `ToolConfirmationRequired` while marking session active task as `"WAITING_FOR_CONFIRMATION"`.

### Maintained & Verified
- 100% backward compatibility with AURA 0.1 – 0.7.
- Zero modifications to SQLite database schema (`data/aura.db`).
- 227/227 automated tests passing.
- 0 Ruff lint errors and 0 Mypy type errors.
