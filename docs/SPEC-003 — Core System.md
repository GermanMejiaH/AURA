# SPEC-003 — Core System

**Proyecto:** AURA (Adaptive Unified Reasoning Assistant)

**Documento:** SPEC-003

**Título:** Core System

**Versión:** 1.0.0

**Estado:** Aprobado

**Fecha:** 05 de agosto de 2026

**Autor:** Equipo de Arquitectura de AURA

---

# 1. Propósito

El Core constituye el núcleo operativo de AURA.

Es responsable de iniciar, coordinar y supervisar el funcionamiento del sistema, proporcionando la infraestructura necesaria para que los módulos cognitivos operen de forma segura y desacoplada.

El Core no implementa inteligencia.

Implementa la plataforma sobre la que la inteligencia funciona.

---

# 2. Objetivos

El Core deberá:

- Gestionar el ciclo de vida del sistema.
- Inicializar módulos.
- Gestionar dependencias.
- Administrar la configuración.
- Supervisar la salud del sistema.
- Coordinar el Event Bus.
- Facilitar la recuperación ante fallos.
- Proporcionar observabilidad.

---

# 3. Arquitectura

El Core estará compuesto por los siguientes servicios.

```text
Core

├── Lifecycle Manager
├── Module Manager
├── Dependency Container
├── Configuration Manager
├── Event Bus
├── Scheduler
├── Health Monitor
├── Logger
└── Diagnostics
```

Cada servicio tendrá una responsabilidad claramente definida.

---

# 4. Lifecycle Manager

## Responsabilidad

Controlar el ciclo de vida completo de AURA.

### Estados

- Booting
- Initializing
- Running
- Degraded
- Shutting Down
- Stopped
- Recovery

Solo el Lifecycle Manager podrá realizar transiciones globales entre estos estados.

---

# 5. Module Manager

Responsable de:

- descubrir módulos;
- cargarlos;
- inicializarlos;
- detenerlos;
- reiniciarlos;
- consultar su estado.

Los módulos no se crearán manualmente.

Serán gestionados por el Core.

---

# 6. Dependency Container

Toda dependencia será resuelta mediante Inversión de Control (IoC).

Los módulos dependerán de interfaces, nunca de implementaciones concretas.

Ejemplos:

- LLMProvider
- AudioProvider
- VisionProvider
- MemoryProvider

Esto permitirá sustituir tecnologías sin modificar la lógica del sistema.

---

# 7. Configuration Manager

Centralizará toda la configuración.

No se permitirá que un módulo lea archivos de configuración directamente.

El acceso se realizará exclusivamente mediante este servicio.

---

# 8. Event Bus

El Event Bus forma parte del Core.

Será el mecanismo oficial de comunicación entre módulos.

Sus responsabilidades se encuentran definidas en ADR-001.

---

# 9. Scheduler

Permitirá programar tareas periódicas o diferidas.

Ejemplos:

- limpieza de memoria temporal;
- sincronización de datos;
- comprobaciones de salud;
- recordatorios;
- mantenimiento interno.

---

# 10. Health Monitor

Supervisará continuamente:

- estado de los módulos;
- disponibilidad de servicios externos;
- uso de recursos;
- sensores;
- herramientas.

Cuando detecte anomalías, publicará eventos para que otros componentes actúen.

---

# 11. Logger

Centralizará el registro del sistema.

Todo módulo utilizará este servicio para registrar información.

El formato de los registros será uniforme y configurable.

---

# 12. Diagnostics

Permitirá obtener información sobre:

- módulos cargados;
- tiempos de inicio;
- consumo de recursos;
- errores recientes;
- estado del sistema;
- métricas.

Su propósito es facilitar el mantenimiento y la depuración.

---

# 13. Ciclo de Arranque

El inicio del sistema seguirá este flujo:

1. Inicializar configuración.
2. Crear el contenedor de dependencias.
3. Iniciar el sistema de logging.
4. Crear el Event Bus.
5. Descubrir módulos.
6. Registrar módulos.
7. Inicializar módulos.
8. Verificar estado de salud.
9. Cargar el Cognitive World Model.
10. Publicar el evento `SystemReady`.
11. Entrar en estado **Running**.

---

# 14. Ciclo de Apagado

El apagado deberá realizarse de forma ordenada.

1. Publicar `SystemShutdownRequested`.
2. Detener nuevas tareas.
3. Finalizar procesos activos.
4. Guardar el estado persistente.
5. Cerrar módulos.
6. Liberar recursos.
7. Registrar el cierre.
8. Cambiar al estado **Stopped**.

---

# 15. Recuperación ante Fallos

Si un módulo presenta un error:

- el fallo será aislado siempre que sea posible;
- el resto del sistema continuará funcionando;
- el Lifecycle Manager evaluará si procede reiniciar el módulo o cambiar el sistema al estado **Degraded**.

La caída de un módulo no deberá provocar la detención completa de AURA, salvo que el fallo comprometa la integridad del sistema.

---

# 16. Restricciones

El Core:

- no implementa lógica cognitiva;
- no razona;
- no almacena conocimiento del mundo;
- no interpreta lenguaje;
- no ejecuta acciones de usuario.

Su responsabilidad es proporcionar la infraestructura común para todos los módulos.

---

# 17. Evolución

En versiones futuras el Core podrá incorporar:

- carga dinámica de módulos;
- múltiples procesos o nodos distribuidos;
- balanceo interno de tareas;
- supervisión remota;
- reinicio automático avanzado;
- alta disponibilidad.

Estas capacidades deberán integrarse sin alterar las responsabilidades fundamentales definidas en esta especificación.

---

# 18. Referencias

- ARCH-001 — Architecture Handbook
- ADR-001 — Arquitectura Basada en Eventos
- ADR-002 — Arquitectura Basada en Estados Cognitivos
- SPEC-001 — Cognitive Architecture
- SPEC-002 — Cognitive World Model
- GUIDE-001 — Development Standards