# ADR-001 — Arquitectura Basada en Eventos

**Proyecto:** AURA (Adaptive Unified Reasoning Assistant)  
**Documento:** ADR-001  
**Título:** Adopción de una Arquitectura Basada en Eventos (Event-Driven Architecture)  
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

AURA está concebido como un sistema cognitivo compuesto por múltiples subsistemas independientes:

- Audio
- Visión
- Memoria
- Planificación
- Herramientas
- Robótica
- Interfaces
- Inteligencia Artificial

Cada uno evolucionará a ritmos diferentes y podrá ser sustituido en el futuro.

Por esta razón, la arquitectura elegida debe minimizar el acoplamiento entre componentes y facilitar el crecimiento continuo del sistema.

---

# 2. Problema

Si cada módulo conoce directamente a los demás, la complejidad aumenta rápidamente.

Ejemplo:

Audio llama a Memory.

Memory llama a Brain.

Brain llama a Vision.

Vision llama a Planner.

Planner llama nuevamente a Audio.

Con el crecimiento del proyecto aparecen:

- Dependencias circulares.
- Código difícil de mantener.
- Integraciones frágiles.
- Alta probabilidad de errores.
- Dificultad para realizar pruebas.

Esta arquitectura no escala adecuadamente.

---

# 3. Decisión

Se adopta una **Arquitectura Basada en Eventos (Event-Driven Architecture)** como mecanismo principal de comunicación entre módulos.

Los módulos no deberán comunicarse directamente entre sí.

En su lugar, publicarán eventos en un bus central y reaccionarán únicamente a los eventos de su interés.

---

# 4. Objetivos de la Decisión

La comunicación basada en eventos permitirá:

- Reducir el acoplamiento.
- Facilitar la extensibilidad.
- Mejorar la mantenibilidad.
- Simplificar las pruebas.
- Permitir la ejecución paralela.
- Incorporar nuevos módulos sin modificar los existentes.

---

# 5. Arquitectura Conceptual

```
                 CORE

                  │

             Event Bus

 ┌────────┬────────┬────────┬────────┐
 │        │        │        │        │
Audio   Vision  Memory  Sensors  Tools
 │        │        │        │        │
 └────────┴────────┴────────┴────────┘
                  │
                Brain
                  │
               Planner
                  │
               Actions
```

El Event Bus será el mecanismo oficial de comunicación del sistema.

---

# 6. ¿Qué es un Evento?

Un evento representa un hecho que ocurrió dentro del sistema.

No expresa una orden.

No representa una función.

Simplemente comunica que algo sucedió.

Ejemplos:

- WakeWordDetected
- SpeechRecognized
- FaceRecognized
- ObjectDetected
- BatteryLow
- UserArrivedHome
- InternetDisconnected
- ReminderTriggered
- ToolFinished

---

# 7. Flujo General

Ejemplo:

1. El módulo Audio detecta la palabra de activación.
2. Audio publica el evento `WakeWordDetected`.
3. El Brain recibe el evento.
4. El Brain cambia de estado a "escuchando".
5. El módulo Audio comienza la captura de voz.
6. Se publica `SpeechRecognized`.
7. El Brain interpreta el contenido.
8. El Planner decide una acción.
9. Se publica un nuevo evento.
10. El módulo correspondiente ejecuta la tarea.

Cada componente únicamente conoce el evento, no el funcionamiento interno de los demás módulos.

---

# 8. Responsabilidades del Event Bus

El Event Bus deberá ser responsable de:

- Registrar eventos.
- Distribuir eventos.
- Gestionar suscripciones.
- Permitir múltiples consumidores.
- Mantener bajo acoplamiento.
- Facilitar la observabilidad del sistema.

No deberá contener lógica de negocio.

---

# 9. Beneficios

## Modularidad

Los módulos pueden desarrollarse independientemente.

---

## Escalabilidad

Agregar nuevos componentes no requiere modificar los existentes.

---

## Extensibilidad

Nuevas funcionalidades podrán incorporarse simplemente escuchando eventos existentes.

---

## Pruebas

Cada módulo podrá probarse publicando eventos simulados.

---

## Observabilidad

Será posible registrar toda la actividad del sistema únicamente observando el flujo de eventos.

---

## Paralelismo

Múltiples módulos podrán reaccionar simultáneamente al mismo evento.

---

# 10. Riesgos

La arquitectura basada en eventos también introduce desafíos.

Entre ellos:

- Mayor complejidad inicial.
- Seguimiento más difícil del flujo de ejecución.
- Riesgo de exceso de eventos.
- Posibles problemas de sincronización.
- Mayor necesidad de documentación.

Estos riesgos se consideran aceptables frente a los beneficios obtenidos.

---

# 11. Principios de Diseño

Todo evento deberá cumplir las siguientes reglas.

## 11.1 Representar un hecho

Correcto:

- VoiceDetected
- DoorOpened

Incorrecto:

- OpenDoor
- SpeakNow

Los eventos describen lo ocurrido.

Las acciones son responsabilidad de otros módulos.

---

## 11.2 Ser inmutable

Un evento nunca deberá modificarse después de ser publicado.

---

## 11.3 Ser autocontenido

Cada evento deberá transportar toda la información necesaria para ser interpretado.

---

## 11.4 Tener nombre consistente

Todos los nombres seguirán PascalCase.

Ejemplos:

- FaceRecognized
- UserArrived
- CameraStarted

---

## 11.5 Ser independiente

Un evento nunca asumirá que otro evento ocurrió previamente.

---

# 12. Impacto sobre la Arquitectura

Esta decisión afecta a todos los módulos presentes y futuros.

Todo nuevo componente deberá integrarse mediante eventos.

No se permitirán dependencias directas entre módulos salvo aquellas definidas explícitamente por la arquitectura.

---

# 13. Alternativas Consideradas

## Comunicación Directa

Ventajas:

- Implementación sencilla.
- Fácil de comprender.

Desventajas:

- Alto acoplamiento.
- Escasa escalabilidad.
- Difícil mantenimiento.

**Descartada.**

---

## Arquitectura Cliente-Servidor Interna

Ventajas:

- Centralización.

Desventajas:

- El servidor termina concentrando demasiadas responsabilidades.

**Descartada.**

---

## Arquitectura Basada en Eventos

Ventajas:

- Bajo acoplamiento.
- Escalabilidad.
- Flexibilidad.
- Modularidad.
- Excelente mantenibilidad.

**Seleccionada.**

---

# 14. Consecuencias

Como consecuencia de esta decisión:

- Todos los módulos deberán publicar eventos.
- Todos los módulos podrán suscribirse a eventos.
- El Brain actuará principalmente como coordinador cognitivo, no como canal obligatorio de comunicación.
- La evolución futura del sistema será considerablemente más sencilla.

---

# 15. Estado

Esta decisión se considera **fundacional**.

Solo podrá modificarse mediante un nuevo ADR que justifique técnicamente el cambio y analice su impacto sobre toda la arquitectura del proyecto.

---

# Referencias

- VISION-001 — Vision Document
- Futuro SPEC-001 — Core
- Futuro SPEC-002 — Event Bus
- Futuro SPEC-003 — Brain