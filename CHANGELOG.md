# CHANGELOG

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
