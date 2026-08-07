# ADR-002 — Arquitectura Basada en Estados Cognitivos

**Proyecto:** AURA (Adaptive Unified Reasoning Assistant)  
**Documento:** ADR-002  
**Título:** Adopción de una Máquina de Estados Cognitiva (Cognitive State Machine)  
**Versión:** 1.0.0  
**Estado:** Aprobado  
**Fecha:** 05 de agosto de 2026  
**Autor:** Equipo de Arquitectura de AURA

---

# Historial de Versiones

| Versión | Fecha | Descripción | Estado |
|----------|------------|----------------------------|-----------|
| 1.0.0 | 05/08/2026 | Primera versión | Aprobado |

---

# 1. Contexto

El documento ADR-001 establece que AURA utilizará una Arquitectura Basada en Eventos para comunicar sus módulos.

Sin embargo, una arquitectura basada únicamente en eventos resulta insuficiente para modelar un comportamiento inteligente.

Un mismo evento puede requerir respuestas completamente diferentes dependiendo de la situación actual del sistema.

Por esta razón, AURA deberá mantener un estado cognitivo interno permanente.

---

# 2. Problema

Supongamos el siguiente evento:

```
VoiceDetected
```

¿Qué debería hacer AURA?

La respuesta depende del contexto.

Si AURA está apagada:

→ Ignorar.

Si está esperando la palabra de activación:

→ Escuchar.

Si ya está conversando:

→ Continuar la conversación.

Si está reproduciendo música:

→ Reducir volumen automáticamente.

Si está ejecutando una tarea crítica:

→ Posponer la conversación.

El evento por sí solo no contiene suficiente información para decidir.

---

# 3. Decisión

Se adopta una Máquina de Estados Cognitiva como mecanismo para controlar el comportamiento global del sistema.

Todos los eventos serán interpretados considerando el estado actual del cerebro.

Los estados definirán qué acciones están permitidas, cuáles deben ignorarse y cuáles implican una transición hacia otro estado.

---

# 4. Objetivos

La Máquina de Estados permitirá:

- Mantener contexto interno.
- Evitar comportamientos incoherentes.
- Reducir decisiones ambiguas.
- Facilitar la planificación.
- Mejorar la comprensión del entorno.
- Modelar comportamientos complejos de forma sencilla.

---

# 5. Principio Fundamental

Los eventos describen **lo que ocurrió**.

Los estados describen **cómo se encuentra AURA**.

Las acciones describen **qué hará AURA**.

Los tres conceptos nunca deberán mezclarse.

---

# 6. Modelo Cognitivo

```
Evento

↓

Brain

↓

Estado Actual

↓

Decisión

↓

Acción

↓

Nuevo Estado
```

---

# 7. Estados Iniciales

La primera versión del sistema utilizará los siguientes estados.

## Booting

Inicialización del sistema.

Carga de módulos.

Configuración.

Verificación de componentes.

---

## Idle

Estado por defecto.

AURA permanece disponible.

Monitorea el entorno.

Espera nuevos eventos.

---

## Listening

Captura voz.

Procesa audio.

Ignora tareas no prioritarias.

---

## Thinking

Analiza contexto.

Consulta memoria.

Planifica acciones.

Genera respuesta.

---

## Speaking

Produce audio.

Supervisa interrupciones.

Gestiona turnos de conversación.

---

## Executing

Ejecuta herramientas.

Automatiza tareas.

Controla dispositivos.

---

## Observing

Analiza cámaras.

Procesa sensores.

Construye representación del entorno.

---

## Learning

Actualiza memoria.

Extrae conocimiento.

Relaciona experiencias.

---

## Sleeping

Reduce actividad.

Permanece atento únicamente a eventos esenciales.

---

## Error

Estado seguro.

Permite recuperación.

Registra diagnóstico.

---

# 8. Transiciones

Ejemplo simplificado.

```
Booting

↓

Idle

↓

Listening

↓

Thinking

↓

Speaking

↓

Idle
```

Otro ejemplo.

```
Idle

↓

Executing

↓

Thinking

↓

Idle
```

El flujo dependerá siempre de los eventos recibidos.

---

# 9. Reglas

## Un único estado principal

AURA solo podrá tener un estado cognitivo principal activo.

No existirá más de un estado dominante simultáneamente.

---

## Subestados

Cada estado podrá contener subestados.

Ejemplo:

Speaking

- Respondiendo
- Leyendo texto
- Narrando
- Confirmando acción

---

## Prioridades

Algunos estados tendrán prioridad sobre otros.

Por ejemplo:

Emergency

tendrá prioridad sobre

Speaking

---

## Transiciones explícitas

Toda transición deberá estar documentada.

No existirán cambios implícitos de estado.

---

# 10. Beneficios

## Comportamiento coherente

El mismo evento generará respuestas consistentes.

---

## Fácil depuración

Será posible conocer el estado interno en cualquier momento.

---

## Mejor planificación

El planificador conocerá exactamente qué puede hacer el sistema.

---

## Mayor realismo

El comportamiento será similar al de un asistente humano.

---

## Escalabilidad

Nuevos estados podrán incorporarse sin modificar los existentes.

---

# 11. Riesgos

- Incremento de la complejidad inicial.
- Mayor número de transiciones.
- Necesidad de documentar todos los cambios de estado.

Estos riesgos son aceptables debido a las ventajas obtenidas.

---

# 12. Relación con la Arquitectura

La Máquina de Estados no reemplaza la Arquitectura Basada en Eventos.

Ambas trabajan conjuntamente.

Eventos → producen cambios de estado.

Estados → determinan las decisiones.

Decisiones → generan acciones.

Acciones → producen nuevos eventos.

---

# 13. Restricciones

Los módulos de Audio, Visión, Memoria y Herramientas no podrán modificar directamente el estado cognitivo.

Solo el Brain tendrá autoridad para realizar transiciones de estado.

Esto garantiza consistencia y evita conflictos.

---

# 14. Consecuencias

Todos los módulos futuros deberán consultar el estado actual antes de ejecutar acciones que dependan del contexto.

Las nuevas funcionalidades deberán definir explícitamente:

- Qué estados utilizan.
- Qué eventos aceptan.
- Qué transiciones producen.

---

# 15. Estado

Esta decisión se considera fundacional y complementa al ADR-001.

Toda evolución futura del Brain deberá respetar este modelo de estados cognitivos.

---

# Referencias

- VISION-001 — Vision Document
- ADR-001 — Arquitectura Basada en Eventos
- Futuro SPEC-003 — Brain