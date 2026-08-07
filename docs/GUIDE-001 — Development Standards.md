# GUIDE-001 — Development Standards

**Proyecto:** AURA (Adaptive Unified Reasoning Assistant)  
**Documento:** GUIDE-001  
**Título:** Development Standards  
**Versión:** 1.0.0  
**Estado:** Activo  
**Fecha:** 05 de agosto de 2026  
**Autor:** Equipo de Arquitectura de AURA

---

# Prefacio

Este documento establece los estándares de desarrollo oficiales del proyecto AURA.

Su propósito es garantizar consistencia, calidad y mantenibilidad durante todo el ciclo de vida del proyecto.

Todas las contribuciones deberán cumplir estas normas.

---

# 1. Objetivos

Los estándares buscan asegurar que el código de AURA sea:

- Claro.
- Consistente.
- Fácil de mantener.
- Fácil de probar.
- Fácil de documentar.
- Independiente de tecnologías específicas.

---

# 2. Lenguaje Principal

El lenguaje principal del proyecto será **Python**.

Las razones incluyen:

- Amplio ecosistema para IA y robótica.
- Excelente soporte para prototipado.
- Gran disponibilidad de librerías.
- Curva de aprendizaje adecuada.

Otros lenguajes podrán incorporarse cuando exista una justificación técnica (por ejemplo, C++ para componentes de alto rendimiento o Rust para módulos críticos), siempre mediante interfaces bien definidas.

---

# 3. Convenciones de Código

## 3.1 Estilo

El código seguirá **PEP 8**.

El formato será aplicado automáticamente mediante herramientas.

No se aceptarán diferencias de estilo manuales.

---

## 3.2 Nombres

Variables y funciones:

```text
snake_case
```

Clases:

```text
PascalCase
```

Constantes:

```text
UPPER_SNAKE_CASE
```

Eventos:

```text
PascalCase
```

Ejemplos:

- VoiceDetected
- UserArrived
- BatteryLow

Interfaces y clases abstractas:

Se utilizarán nombres descriptivos, por ejemplo:

- MemoryProvider
- AudioInterface
- EventPublisher

---

## 3.3 Tipado

Todo el código nuevo deberá utilizar **type hints**.

Ejemplo:

```python
def search_memory(query: str) -> list[str]:
    ...
```

El tipado forma parte del diseño, no es opcional.

---

# 4. Estructura de Módulos

Cada módulo importante deberá incluir, como mínimo:

```text
module_name/
├── README.md
├── architecture.md
├── api.md
├── CHANGELOG.md
├── src/
├── tests/
└── docs/
```

La implementación, las pruebas y la documentación deberán evolucionar conjuntamente.

---

# 5. Gestión de Versiones

Se utilizará **Git**.

### Estrategia inicial

Mientras el proyecto tenga un único desarrollador:

- Rama principal: `main`
- Rama de desarrollo para nuevas funcionalidades: `feature/<nombre>`
- Correcciones: `fix/<nombre>`
- Documentación: `docs/<nombre>`

Si el equipo crece, esta estrategia podrá revisarse mediante un ADR.

---

# 6. Convención de Commits

Se adoptará el estándar **Conventional Commits**.

Ejemplos:

```text
feat(memory): add episodic memory

fix(audio): prevent duplicated recording

docs(architecture): update event flow

refactor(core): simplify lifecycle

test(event_bus): add publish tests
```

Cada commit deberá representar un cambio coherente y atómico.

---

# 7. Documentación

Toda funcionalidad nueva deberá actualizar la documentación correspondiente.

La documentación mínima incluye:

- Descripción.
- Responsabilidades.
- Interfaces públicas.
- Dependencias.
- Limitaciones conocidas.

La documentación no es opcional.

---

# 8. Pruebas

Todo módulo deberá incluir pruebas automatizadas.

Se distinguen los siguientes niveles:

- Unitarias.
- Integración.
- Sistema (cuando corresponda).

El objetivo no es alcanzar un porcentaje arbitrario de cobertura, sino asegurar que los comportamientos críticos estén verificados.

---

# 9. Registro de Eventos (Logging)

No se utilizará `print()` para registrar información del sistema.

Todo registro deberá realizarse mediante el sistema oficial de logging.

Niveles permitidos:

- DEBUG
- INFO
- WARNING
- ERROR
- CRITICAL

Cada módulo deberá generar registros útiles para diagnóstico sin revelar información sensible.

---

# 10. Manejo de Errores

No se permitirán capturas genéricas que oculten fallos.

Incorrecto:

```python
try:
    ...
except:
    pass
```

Correcto:

- Capturar excepciones específicas.
- Registrar el error.
- Recuperarse cuando sea posible.
- Propagar el error cuando corresponda.

---

# 11. Calidad Estática

Antes de integrarse en `main`, el código deberá superar:

- Formateo automático.
- Linter.
- Verificación de tipos.
- Ejecución de pruebas.

Las herramientas concretas podrán evolucionar, pero inicialmente se recomienda:

- Black
- Ruff
- MyPy
- Pytest

---

# 12. Principios Arquitectónicos Obligatorios

Todo componente deberá respetar las siguientes reglas:

- Los módulos se comunican mediante el Event Bus.
- Ningún módulo accede directamente al hardware de otro.
- El Brain no contiene lógica de acceso a dispositivos.
- La Memoria no ejecuta acciones.
- La Visión no toma decisiones.
- El Planner no ejecuta tareas.
- El Action Coordinator no razona.

---

# 13. Seguridad

Las credenciales, claves y configuraciones sensibles nunca deberán almacenarse en el código fuente.

Se utilizarán mecanismos de configuración externos y adecuados para cada entorno.

---

# 14. Definición de Terminado (Definition of Done)

Una tarea solo se considerará completada cuando:

- Cumpla el objetivo funcional.
- Respete la arquitectura.
- Esté documentada.
- Incluya pruebas apropiadas.
- Maneje errores correctamente.
- Genere registros relevantes.
- Utilice tipado.
- Cumpla las convenciones de estilo.
- No introduzca deuda técnica conocida sin documentarla.

"Funciona" no equivale a "está terminado".

---

# 15. Revisión de Cambios

Antes de aceptar una modificación importante deberán responderse, como mínimo, las siguientes preguntas:

1. ¿Respeta la arquitectura existente?
2. ¿Reduce o incrementa el acoplamiento?
3. ¿Es comprensible para otro desarrollador?
4. ¿Está documentada?
5. ¿Es fácil de probar?
6. ¿Puede evolucionar sin romper otros módulos?
7. ¿Existe una solución más simple?

Si alguna respuesta es negativa, el cambio deberá revisarse.

---

# 16. Evolución

Este documento podrá actualizarse cuando el crecimiento del proyecto lo requiera.

Toda modificación relevante deberá registrarse en el historial de versiones y, si afecta a decisiones arquitectónicas, justificarse mediante un ADR.

---

# Referencias

- GUIDE-000 — Engineering Philosophy
- ARCH-001 — Architecture Handbook
- VISION-001 — Vision Document
- ADR-001 — Arquitectura Basada en Eventos
- ADR-002 — Arquitectura Basada en Estados Cognitivos