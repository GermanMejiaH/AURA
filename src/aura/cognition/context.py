from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .working_memory import WorkingMemory

if TYPE_CHECKING:
    from ..container import DependencyContainer
    from .identity import AURAIdentity
    from .session import SessionContext


@dataclass
class CognitiveContext:
    """Encapsulates structured cognitive context compiled for LLM reasoning."""

    system_instruction: str
    user_input: str
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    working_memory_summary: str = ""
    world_entities: list[str] = field(default_factory=list)
    relevant_memories: list[str] = field(default_factory=list)
    available_tools: list[dict[str, str]] = field(default_factory=list)
    identity: AURAIdentity | None = None
    session_context: SessionContext | None = None

    def to_system_prompt(self) -> str:
        """Formats identity, background context, memory, and tools into a system prompt."""
        parts: list[str] = []

        if self.identity is not None:
            parts.append(
                f"[IDENTIDAD DE AURA]: Nombre: {self.identity.name} | "
                f"Misión: {self.identity.mission} | "
                f"Estilo: {self.identity.personality_style} | Idioma: {self.identity.language}"
            )

        parts.append(self.system_instruction)

        if self.session_context is not None:
            sess_info: list[str] = []
            if self.session_context.current_topic:
                sess_info.append(f"Tema: {self.session_context.current_topic}")
            if self.session_context.active_task:
                sess_info.append(f"Tarea: {self.session_context.active_task}")
            if self.session_context.last_intent:
                sess_info.append(f"Intención reciente: {self.session_context.last_intent}")
            if sess_info:
                parts.append(f"[ESTADO CONTEXTUAL DE SESIÓN]: {', '.join(sess_info)}")

        if self.available_tools:
            names = [f"'{t.get('name')}'" for t in self.available_tools if t.get("name")]
            tools_str = ", ".join(names)
            parts.append(f"Herramientas digitales registradas en el sistema: [{tools_str}].")

        if self.world_entities:
            entities_str = ", ".join(self.world_entities[:10])
            parts.append(f"Entidades percibidas en el entorno (CWM): [{entities_str}].")

        if self.relevant_memories:
            parts.append("\nRECUERDOS DE MEMORIA PERSISTENTE DEL USUARIO:")
            for m in self.relevant_memories[:5]:
                parts.append(f"  • {m}")

        return "\n".join(parts)

    def to_formatted_prompt(self) -> str:
        """Formats conversational history and current input for LLM prompt."""
        parts: list[str] = []

        if self.conversation_history:
            parts.append("Historial conversacional reciente:")
            for turn in self.conversation_history[-12:]:
                role = "Usuario" if turn.get("role") == "user" else "AURA"
                parts.append(f"  [{role}]: {turn.get('content', '')}")
            parts.append("")

        parts.append(f"Usuario: {self.user_input}")
        return "\n".join(parts)


class CognitiveContextBuilder:
    """Compiles structured CognitiveContext from container modules."""

    DEFAULT_INSTRUCTION = (
        "Eres AURA (Adaptive Unified Reasoning Assistant), un asistente cognitivo inteligente y "
        "autónomo. Respondes siempre en español de forma natural, concisa y directa por voz "
        "(máximo 1 a 3 oraciones breves). "
        "REGLA DE MEMORIA: Si el usuario pregunta sobre datos personales, gustos o hechos "
        "pasados y la respuesta está presente en 'RECUERDOS DE MEMORIA PERSISTENTE DEL USUARIO', "
        "DEBES responder utilizando explícitamente dicha información. "
        "NUNCA afirmes que no recuerdas, que no tienes acceso a la información o que no puedes "
        "recordar conversaciones pasadas si el dato está presente en la memoria."
    )

    def __init__(self, container: DependencyContainer | None = None) -> None:
        self.container = container

    def build(
        self,
        input_text: str,
        system_instruction: str = "",
        working_memory: WorkingMemory | None = None,
    ) -> CognitiveContext:
        instruction = system_instruction or self.DEFAULT_INSTRUCTION

        history: list[dict[str, str]] = []
        if working_memory is not None:
            history = working_memory.get_recent_conversation(limit=12)

        world_entities: list[str] = []
        relevant_memories: list[str] = []
        available_tools: list[dict[str, str]] = []
        identity_obj = None
        session_obj = None

        if self.container is not None:
            # Pull IdentityManager if available
            try:
                from .identity import IdentityManager

                if self.container.has(IdentityManager):
                    identity_obj = self.container.resolve(IdentityManager).get_identity()
            except Exception:
                pass

            # Pull SessionManager if available
            try:
                from .session import SessionManager

                if self.container.has(SessionManager):
                    session_obj = self.container.resolve(SessionManager).get_context()
            except Exception:
                pass

            # Pull CWM entities if available
            try:
                from ..world import CognitiveWorldModel

                if self.container.has(CognitiveWorldModel):
                    cwm = self.container.resolve(CognitiveWorldModel)
                    world_entities = [
                        f"{e.name} ({getattr(e.type, 'value', str(e.type))})"
                        for e in cwm.all_entities()
                    ]
            except Exception:
                pass

            # Pull Memory facts/preferences if available
            try:
                from ..memory import MemoryModule

                if self.container.has(MemoryModule):
                    mem = self.container.resolve(MemoryModule)
                    retrieval = mem.retrieval.query(input_text)
                    relevant_memories = [
                        f"[{f.predicate} del {f.subject}]: {f.object_val}"
                        for f in retrieval.facts
                    ] + [f"[{p.key}]: {p.value}" for p in retrieval.preferences]
            except Exception:
                pass

            # Pull Tools metadata if available
            try:
                from ..tools import ToolRegistry

                if self.container.has(ToolRegistry):
                    reg = self.container.resolve(ToolRegistry)
                    available_tools = [
                        {"name": meta.name, "description": meta.description}
                        for meta in reg.list_metadata()
                    ]
            except Exception:
                pass

        return CognitiveContext(
            system_instruction=instruction,
            user_input=input_text,
            conversation_history=history,
            world_entities=world_entities,
            relevant_memories=relevant_memories,
            available_tools=available_tools,
            identity=identity_obj,
            session_context=session_obj,
        )
