# ROADMAP-001 — Product Roadmap

**Proyecto:** AURA (Adaptive Unified Reasoning Assistant)

**Documento:** ROADMAP-001

**Título:** Product Roadmap

**Versión:** 1.0.0

**Estado:** Activo

**Fecha:** 06 de agosto de 2026

**Autor:** Equipo de Arquitectura de AURA

---

# 1. Propósito

Este documento define la evolución planificada del proyecto AURA.

Cada fase representa un incremento funcional sobre una arquitectura estable.

Las fases deberán ejecutarse en orden, salvo que un ADR aprobado justifique una modificación.

---

# 2. Objetivos del Roadmap

El roadmap tiene cuatro objetivos principales:

- Guiar el desarrollo del proyecto.
- Reducir la complejidad mediante entregas incrementales.
- Permitir validar cada componente antes de avanzar.
- Mantener la coherencia con la arquitectura definida.

---

# 3. Principios

Toda fase deberá:

- Ser funcional por sí misma.
- Tener criterios claros de finalización.
- Añadir valor al sistema.
- No romper funcionalidades anteriores.
- Mantener compatibilidad con la arquitectura.

---

# 4. Fases del Proyecto

## Fase 0 — Arquitectura y Diseño

### Objetivo

Diseñar completamente la arquitectura antes de escribir código.

### Entregables

- Vision.
- Architecture Handbook.
- ADR.
- SPEC.
- GUIDE.
- Roadmap.

### Estado esperado

Proyecto completamente documentado.

---

## Fase 1 — Foundation

### Objetivo

Construir la infraestructura mínima del sistema.

### Componentes

- Core.
- Event Bus.
- Configuration Manager.
- Logging.
- Dependency Container.
- Lifecycle Manager.

### Resultado esperado

AURA puede iniciar y detenerse correctamente.

---

## Fase 2 — Cognitive World Model

### Objetivo

Implementar el modelo interno del mundo.

### Componentes

- Entidades.
- Relaciones.
- Persistencia.
- Consultas.
- Actualización mediante eventos.

### Resultado esperado

AURA mantiene una representación persistente del entorno.

---

## Fase 3 — Cognitive Engine

### Objetivo

Implementar el procesamiento cognitivo.

### Componentes

- Attention Manager.
- Working Memory.
- Reasoning Engine.
- Decision Engine.
- Planner.

### Resultado esperado

AURA puede razonar sobre el estado del mundo.

---

## Fase 4 — Audio

### Objetivo

Permitir interacción mediante voz.

### Componentes

- Wake Word.
- Speech to Text.
- Text to Speech.
- Detección de silencio.
- Gestión de conversaciones.

### Resultado esperado

Conversación por voz estable.

---

## Fase 5 — Vision

### Objetivo

Incorporar percepción visual.

### Componentes

- Cámara.
- Detección de personas.
- Objetos.
- Rostros.
- OCR.
- Integración con el CWM.

### Resultado esperado

AURA comprende el entorno visual inmediato.

---

## Fase 6 — Memory

### Objetivo

Implementar memoria persistente avanzada.

### Componentes

- Episodic Memory.
- Semantic Memory.
- Preferences.
- Retrieval.
- Consolidación.

### Resultado esperado

Conversaciones continuas durante semanas o meses.

---

## Fase 7 — Tools

### Objetivo

Controlar aplicaciones y servicios externos.

### Ejemplos

- Spotify.
- Navegador.
- Calendario.
- Archivos.
- Correo.
- APIs.

### Resultado esperado

AURA ejecuta acciones útiles en el entorno digital.

---

## Fase 8 — Robotics

### Objetivo

Controlar un cuerpo físico.

### Componentes

- Motores.
- Sensores.
- Navegación.
- Manipulación.
- Seguridad.

### Resultado esperado

AURA interactúa físicamente con el entorno.

---

## Fase 9 — Autonomía

### Objetivo

Permitir comportamiento parcialmente autónomo.

### Capacidades

- Gestión de objetivos.
- Priorización.
- Planificación prolongada.
- Aprendizaje continuo.
- Adaptación.

### Resultado esperado

AURA puede ejecutar objetivos complejos con mínima supervisión.

---

# 5. Hitos Principales

## Hito 1

Primer inicio exitoso del Core.

---

## Hito 2

Primer evento procesado correctamente.

---

## Hito 3

Primer conocimiento almacenado en el CWM.

---

## Hito 4

Primera conversación por voz.

---

## Hito 5

Primer reconocimiento visual.

---

## Hito 6

Primera herramienta controlada.

---

## Hito 7

Primer robot controlado.

---

## Hito 8

Primer objetivo ejecutado de forma autónoma.

---

# 6. Criterios de Finalización de una Fase

Una fase solo se considerará terminada cuando:

- Todos sus objetivos estén implementados.
- Existan pruebas suficientes.
- La documentación esté actualizada.
- No existan errores críticos abiertos.
- El sistema mantenga compatibilidad con fases anteriores.
- Se hayan registrado las decisiones arquitectónicas relevantes.

---

# 7. Gestión de Cambios

El roadmap es un documento vivo.

Podrá modificarse cuando:

- Surjan nuevos requisitos.
- Cambie la arquitectura.
- Se aprenda una mejor estrategia de implementación.

Toda modificación importante deberá quedar registrada.

---

# 8. Visión a Largo Plazo

La versión inicial de AURA representa únicamente el comienzo del proyecto.

La arquitectura está diseñada para permitir años de evolución sin necesidad de rediseñar sus fundamentos.

Cada fase construye sobre la anterior.

La estabilidad de la arquitectura tiene prioridad sobre la velocidad de desarrollo.

---

# Referencias

- VISION-001 — Vision Document
- ARCH-001 — Architecture Handbook
- GUIDE-000 — Engineering Philosophy
- GUIDE-001 — Development Standards
- SPEC-001 — Cognitive Architecture
- SPEC-002 — Cognitive World Model
- SPEC-003 — Core System
- ADR-001 — Arquitectura Basada en Eventos
- ADR-002 — Arquitectura Basada en Estados Cognitivos