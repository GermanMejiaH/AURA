# AURA — Manual de Módulos (Modules Developer Guide)

Este documento ofrece una guía de referencia técnica para desarrolladores sobre los **8 módulos centrales** que integran la plataforma AURA.

---

## 1. CWMModule (`aura.world`)

### Descripción
El **Cognitive World Model (CWM)** gestiona la representación simbólica del mundo mediante un grafo persistente en disco de entidades y relaciones de conocimiento.

- **Prioridad**: `10`
- **IoC Container**: Registra `CognitiveWorldModel`, `WorldQueryEngine`, `CWMPersistenceProvider`.
- **Suscripciones**: `EntityCreated`, `EntityUpdated`, `EntityDeleted`, `RelationCreated`, `RelationDeleted`.
- **Eventos Emitidos**: `WorldModelUpdated`.

### Ejemplo de Uso
```python
from aura.world import CognitiveWorldModel, Entity, EntityType

cwm = CognitiveWorldModel()
entity = Entity(name="Escritorio", type=EntityType.OBJECT)
cwm.add_entity(entity)
print(cwm.all_entities())
```

---

## 2. CognitionModule (`aura.cognition`)

### Descripción
Representa la máquina de estados cognitivos (`Idle`, `Attending`, `Reasoning`, `Planning`, `Executing`, `Reflecting`), la memoria de trabajo temporal (`WorkingMemory`), el planificador de acciones y el motor de decisiones.

- **Prioridad**: `20`
- **IoC Container**: Registra `WorkingMemory`, `CognitiveStateMachine`, `Planner`, `ActionCoordinator`, `DecisionEngine`, `AttentionManager`.
- **Suscripciones**: `SpeechRecognized`, `VisualSceneProcessed`, `GoalSet`, `StepExecuted`.
- **Eventos Emitidos**: `CognitiveStateChanged`, `PlanCreated`, `ActionDispatched`, `AttentionFocused`.

---

## 3. AudioModule (`aura.audio`)

### Descripción
Monitorea la entrada y salida de audio mediante proveedores STT (Speech-to-Text), TTS (Text-to-Speech), detector de palabra de activación (*Wake Word*) y detector de silencio.

- **Prioridad**: `30`
- **IoC Container**: Registra `STTProvider`, `TTSProvider`, `WakeWordDetector`, `SilenceDetector`.
- **Suscripciones**: `AudioPlaybackStarted`, `AudioPlaybackFinished`.
- **Eventos Emitidos**: `WakeWordDetected`, `SpeechRecognized`, `SpeechSynthesized`, `SilenceDetected`.

---

## 4. VisionModule (`aura.vision`)

### Descripción
Procesa la entrada de la cámara, realiza OCR de texto, reconocimiento facial, detección de personas y objetos en el entorno visual.

- **Prioridad**: `35`
- **IoC Container**: Registra `CameraProvider`, `FaceRecognizer`, `PersonDetector`, `OCRProcessor`.
- **Suscripciones**: `FrameCaptured`.
- **Eventos Emitidos**: `VisualSceneProcessed`, `ObjectDetected`, `PersonDetected`, `FaceRecognized`, `TextRecognized`.

---

## 5. MemoryModule (`aura.memory`)

### Descripción
Administra la memoria a largo plazo organizada en 3 subsistemas: memoria episódica (historial de eventos), semántica (hechos conceptuales) y preferencias de usuario, respaldada por un motor de consolidación.

- **Prioridad**: `25`
- **IoC Container**: Registra `EpisodicMemory`, `SemanticMemory`, `UserPreferencesMemory`, `MemoryRetrievalEngine`, `MemoryConsolidator`.
- **Suscripciones**: `SpeechRecognized`, `GoalAchieved`.
- **Eventos Emitidos**: `EpisodeRecorded`, `FactLearned`, `PreferenceUpdated`, `MemoryConsolidated`, `MemoryQueried`.

---

## 6. ToolsModule (`aura.tools`)

### Descripción
Administra el registro dinámico de herramientas externas y despacha su ejecución segura en respuesta a intenciones cognitivas.

- **Prioridad**: `40`
- **IoC Container**: Registra `ToolRegistry`.
- **Suscripciones**: `ActionDispatched`.
- **Eventos Emitidos**: `ToolRegistered`, `ToolExecuted`, `ToolFailed`.

### Herramientas Integradas
- `FileTool`: Manipulación de archivos.
- `BrowserTool`: Simulación de navegación web.
- `CalendarTool`: Programación de reuniones y eventos.
- `SpotifyTool`: Control multimedia.
- `EmailTool`: Lectura y envío de mensajes.
- `APITool`: Peticiones REST HTTP.

---

## 7. RoboticsModule (`aura.robotics`)

### Descripción
Abstrae la interfaz física con motores, sensores de telemetría, navegación por waypoints, manipulación de agarradores y el sistema de paro de emergencia de seguridad (E-Stop).

- **Prioridad**: `55`
- **IoC Container**: Registra `MotorController`, `SensorManager`, `NavigationSystem`, `Manipulator`, `SafetySystem`.
- **Suscripciones**: `ActionDispatched`.
- **Eventos Emitidos**: `MotorMoved`, `SensorDataReceived`, `NavigationTargetReached`, `ObjectManipulated`, `SafetyAlert`, `EmergencyStopTriggered`.

---

## 8. AutonomyModule (`aura.autonomy`)

### Descripción
Módulo de comportamiento semi-autónomo responsable de gestionar objetivos de alto nivel, descomponerlos mediante el planificador prolongado (*Long-Horizon Planner*), priorizarlos dinámicamente y aprender de los resultados.

- **Prioridad**: `60`
- **IoC Container**: Registra `GoalManager`, `PriorityEngine`, `LongHorizonPlanner`, `LearningEngine`.
- **Suscripciones**: `GoalSet`, `GoalAchieved`.
- **Eventos Emitidos**: `GoalCreated`, `GoalStatusChanged`, `GoalPrioritized`, `LongPlanGenerated`, `PolicyUpdated`.
