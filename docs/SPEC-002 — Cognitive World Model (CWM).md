# SPEC-002 — Cognitive World Model (CWM)

**Proyecto:** AURA (Adaptive Unified Reasoning Assistant)

**Documento:** SPEC-002

**Versión:** 1.0.0

**Estado:** Aprobado

**Fecha:** 05 de agosto de 2026

**Autor:** Equipo de Arquitectura de AURA

---

# 1. Propósito

El Cognitive World Model (CWM) es la representación interna del universo conocido por AURA.

Su función consiste en mantener un modelo coherente, persistente y actualizado del entorno, del usuario y del propio sistema.

El CWM constituye la única fuente oficial de verdad sobre el estado del mundo conocido por AURA.

---

# 2. Objetivos

El CWM deberá permitir que AURA:

- Comprenda el entorno.
- Mantenga continuidad entre conversaciones.
- Recuerde relaciones.
- Razone utilizando contexto persistente.
- Localice objetos.
- Conozca personas.
- Conozca lugares.
- Conozca su propio estado interno.

---

# 3. Principios

## 3.1 Fuente única de verdad (Single Source of Truth)

Toda información persistente sobre el mundo deberá almacenarse en el CWM.

Los demás módulos consultarán el CWM, pero no mantendrán copias independientes del estado.

---

## 3.2 Representación mediante grafo

El mundo será modelado como un **grafo de entidades y relaciones**.

Las entidades representan elementos del mundo.

Las relaciones representan cómo interactúan entre sí.

---

## 3.3 Actualización incremental

El modelo no se reconstruye en cada interacción.

Se actualiza únicamente cuando ocurre un evento relevante.

---

## 3.4 Persistencia

El conocimiento relevante deberá sobrevivir entre reinicios del sistema.

---

## 3.5 Incertidumbre

No toda información tendrá el mismo nivel de confianza.

Cada dato podrá incluir:

- nivel de confianza;
- origen;
- fecha de actualización;
- tiempo de validez.

---

# 4. Entidades

El CWM podrá representar, entre otras:

## Personas

- nombre;
- rostro;
- voz;
- preferencias;
- relaciones.

---

## Objetos

- nombre;
- categoría;
- ubicación;
- propietario;
- estado.

---

## Lugares

- habitaciones;
- edificios;
- zonas;
- coordenadas.

---

## Mascotas

- identidad;
- ubicación;
- comportamiento reciente.

---

## Dispositivos

- computador;
- robot;
- sensores;
- cámaras;
- luces;
- IoT.

---

## Tareas

- pendientes;
- ejecutándose;
- completadas.

---

## Conversaciones

- contexto activo;
- referencias;
- temas recientes.

---

## Capacidades

- herramientas disponibles;
- modelos cargados;
- sensores activos.

---

# 5. Relaciones

Ejemplos.

Persona

→ posee → objeto

Objeto

→ está en → habitación

Habitación

→ pertenece a → casa

Usuario

→ alimenta → mascota

Robot

→ observa → habitación

Herramienta

→ puede ejecutar → acción

---

# 6. Atributos

Cada entidad deberá disponer de:

- identificador único;
- tipo;
- atributos;
- relaciones;
- fecha de creación;
- fecha de actualización;
- origen de la información;
- nivel de confianza.

---

# 7. Ciclo de Vida

1. Se detecta un evento.

2. El Perception Manager interpreta el evento.

3. El CWM identifica las entidades involucradas.

4. Se crean o actualizan entidades.

5. Se modifican relaciones.

6. Se recalcula el estado del mundo.

7. Se publica un evento indicando que el CWM ha cambiado.

---

# 8. Consultas

Todos los módulos podrán realizar consultas al CWM mediante interfaces definidas.

Ejemplos conceptuales:

- ¿Dónde está la moto?
- ¿Quién está presente?
- ¿Qué objetos hay en esta habitación?
- ¿Qué herramientas están disponibles?
- ¿Cuál fue la última conversación?

El CWM responderá utilizando el conocimiento almacenado, no realizando nuevas inferencias mediante modelos de IA.

---

# 9. Integración con Memoria

El CWM no reemplaza la memoria.

Ambos componentes colaboran.

**Working Memory**

- Contexto inmediato.
- Información temporal.

**Long-Term Memory**

- Recuerdos persistentes.
- Preferencias.
- Experiencias.

**CWM**

- Estado actual del mundo.
- Relaciones entre entidades.
- Representación estructurada del conocimiento.

---

# 10. Integración con el Brain

El Brain no almacenará conocimiento permanente.

Cuando necesite comprender el contexto deberá consultar el CWM.

El CWM responde.

El Brain razona.

---

# 11. Integración con el LLM

Los modelos de lenguaje no serán responsables de recordar el mundo.

Su función será interpretar, generar lenguaje y razonar utilizando la información proporcionada por el CWM.

El conocimiento persistente permanecerá fuera del modelo.

---

# 12. Calidad del Conocimiento

Toda información deberá registrar:

- fuente;
- momento de adquisición;
- nivel de confianza;
- historial de modificaciones.

Cuando existan datos contradictorios, el sistema conservará ambas versiones hasta disponer de evidencia suficiente.

---

# 13. Restricciones

El CWM:

- no ejecuta acciones;
- no razona;
- no planifica;
- no interpreta lenguaje;
- no controla hardware.

Su responsabilidad es exclusivamente representar el mundo conocido.

---

# 14. Evolución

En futuras versiones el CWM podrá incorporar:

- mapas tridimensionales;
- relaciones temporales;
- predicción de comportamiento;
- conocimiento semántico avanzado;
- múltiples usuarios;
- representación probabilística del entorno.

---

# 15. Declaración Final

El Cognitive World Model constituye el núcleo del conocimiento estructurado de AURA.

Todos los componentes del sistema deberán considerar al CWM como la representación oficial del mundo conocido.

Su propósito no es pensar, sino preservar una visión coherente, persistente y verificable del universo en el que AURA opera.

---

# Referencias

- VISION-001 — Vision Document
- ARCH-001 — Architecture Handbook
- ADR-001 — Arquitectura Basada en Eventos
- ADR-002 — Arquitectura Basada en Estados Cognitivos
- SPEC-001 — Cognitive Architecture