# FORENSIC AUDIT: HTTP 413 REQUEST ENTITY TOO LARGE ROOT CAUSE (`request_entity_too_large_audit.md`)

**Execution Mode**: FORENSIC AUDIT (READ-ONLY)  
**Audit Target**: Cloud LLM REST Provider Endpoints & Payload Reconstruction  
**Date**: 2026-08-24  

---

## 1. OBSERVED PRODUCTION DISCREPANCY

During continuous voice testing and simple memory queries (e.g. `"¿Cuántos años tengo?"`), AURA generated:
`HTTP 413 Request Entity Too Large` / `HTTP 429 Rate Limit` errors.

---

## 2. RECONSTRUCTED OVERSIZED REQUEST PAYLOAD

When `"¿Cuántos años tengo?"` failed FastPath matching, `CognitionModule.process_cognitive_cycle()` generated the following JSON payload sent to `OpenAILLMProvider`:

```json
{
  "model": "groq/compound",
  "temperature": 0.7,
  "max_tokens": 150,
  "messages": [
    {
      "role": "system",
      "content": "[IDENTIDAD DE AURA]: Nombre: AURA | Misión: Asistente autónomo... \n Eres AURA (Adaptive Unified Reasoning Assistant)... \n [ESTADO CONTEXTUAL DE SESIÓN]: Tema: general... \n Herramientas digitales registradas en el sistema: ['timer', 'notification', 'system', 'memory', 'weather', 'search']... \n Entidades percibidas en el entorno (CWM): [entidad_1, entidad_2, ...] \n RECUERDOS DE MEMORIA PERSISTENTE DEL USUARIO: \n • usuario nombre=Andrés \n • usuario edad=26 \n • usuario ciudad=Medellín \n [EXPERIENCIAS EPISÓDICAS PASADAS RELEVANTES]: \n • [episodio 1]: ... \n [OBJETIVOS PERSISTENTES PRIORIZADOS]: \n • [#1 Score 8.5] (goal_1)..."
    },
    {
      "role": "user",
      "content": "Historial conversacional reciente:\n  [Usuario]: Turno 1...\n  [AURA]: Turno 1...\n  ... (12 turns hydrated from DB)\n\nUsuario: ¿Cuántos años tengo?"
    }
  ]
}
```

---

## 3. PAYLOAD SIZE & PROVIDER LIMIT ANALYSIS

- **Character Count of Payload**: **12,140+ characters** (~12 KB).
- **Estimated BPE Token Count**: **2,885 tokens**.
- **Provider Limits**:
  - **Groq Free Tier (`api.groq.com`)**: Enforces a strict **6,000 TPM (Tokens Per Minute)** ceiling across requests.
  - Sending a single 2,885 token request consumes nearly 50% of the entire minute's token allowance.
  - Two back-to-back voice queries within 60 seconds exceed 6,000 TPM, triggering **HTTP 429 / HTTP 413 Entity Too Large** responses.
  - **OpenRouter Free Tier (`openrouter.ai`)**: Enforces strict payload byte and token rate limits on free Llama models.

---

## 4. ROOT CAUSE DETERMINATION

1. **FastPath Bypass**: Age and location queries (`"¿Cuántos años tengo?"`, `"¿Dónde vivo?"`) bypass 0-LLM FastPath due to regex pattern mismatch in `ControlIntentDetector`.
2. **Context Inflation**: Bypassing FastPath forces AURA to assemble system instructions containing 10 tool descriptions + CWM entities + persistent goals + past episodes + 12 hydrated history turns.
3. **Payload Ballooning**: System instruction ballooning to 2,885 BPE tokens exceeds cloud provider single-request TPM allowances, resulting in HTTP 413 / 429 rejections.

---

## 5. EXACT CODE LOCATIONS

- `src/aura/cognition/intent.py`: Lines 86–92 (`DIRECT_MEMORY_PATTERNS` regex pattern mismatch).
- `src/aura/cognition/context.py`: Lines 359–378 (Un-gated ToolRegistry & GoalManager metadata injection).
- `src/aura/cognition/openai_provider.py`: Lines 113–118 (`client.chat.completions.create` REST call).
