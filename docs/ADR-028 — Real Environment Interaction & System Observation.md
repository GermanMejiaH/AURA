# ADR-028: Real Environment Interaction & System Observation Capability Layer

## Context
Following Stage 21 certification (Real Cognitive Provider Integration), AURA 1.6 established persistent cognitive turn processing using Google Gemini (`GeminiLLMProvider`) and schema-validated tool proposals. However, built-in tools (`FileTool`, `APITool`, `BrowserTool`, `SystemStatusTool`) relied on static mock string returns.

Stage 22 expands AURA 1.6 into a complete real assistant capable of observing host OS metrics, executing sandboxed file operations, performing controlled HTTP web retrieval, and processing real speech turns without violating executive authority boundaries.

---

## Decision

1. **Zero Executive Authority for Environment Tools**:
   - All environment capabilities (`RealSystemObservationTool`, `RealSandboxedFileTool`, `RealHTTPRetrievalTool`) are implemented strictly as `BaseTool` subclasses registered in `ToolRegistry`.
   - Executive authority remains 100% within Stage 16 `RuntimeOrchestrator`. No new manager or coordinator abstractions (`EnvironmentManager`, `FileManager`, `SystemManager`) are introduced.

2. **Real Host System Observation (`RealSystemObservationTool`)**:
   - Queries real host OS metrics (`cpu_percent`, `memory_available_mb`, `disk_free_gb`, `platform_info`, `active_process_count`, `network_connected`) via `psutil`, `platform`, and `os`.
   - Operates in read-only mode (`risk_level="safe"`). Suppresses raw secrets or sensitive environment variables.

3. **Real Sandboxed File Operations (`RealSandboxedFileTool`)**:
   - Confines all file reads, writes, directory listings, and existence checks strictly within a workspace sandbox directory (`data/sandbox/`).
   - Enforces strict path resolution via `pathlib.Path.resolve()` and containment checks (`Path.is_relative_to` & `os.path.commonpath`). Rejects path traversal attacks (`../`, `..\`), symlink escapes, and absolute path overrides.

4. **Real HTTP Retrieval & SSRF Protection (`RealHTTPRetrievalTool`)**:
   - Executes safe HTTP GET requests with strict timeouts (5.0s default), maximum payload limits (1MB), and scheme restrictions (`http://`, `https://`).
   - Enforces SSRF defense by inspecting target IP addresses and blocking loopback (`127.0.0.0/8`, `::1`), private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local metadata endpoints (`169.254.0.0/16`), and internal hostnames (`localhost`, `*.local`).
   - Treats all retrieved web content as untrusted data, preventing prompt injection attacks from executing unauthorized tools.

5. **Conversational Voice Adapter (`ConversationalVoiceAdapter`)**:
   - Bridges speech recognition (`STTProvider`) and speech synthesis (`TTSProvider`) with `ConversationalRuntime.process_turn(...)` without introducing a second orchestration loop.

---

## Consequences

- **Capabilities**: AURA 1.6 can now query real system performance, read/write sandboxed files, fetch web API data, and process voice turns.
- **Security & Safety**: Path traversal, SSRF, arbitrary command execution, and prompt injection attacks are completely defended against.
- **Hardware Independence**: Runs on standard PCs without physical camera/robotic hardware.
- **Testability**: 100% offline testable with 20 integration test scenarios (`S22-01` to `S22-20`).
- **Backward Compatibility**: All Stage 10–21 contracts, test suites, and invariants remain 100% intact.
