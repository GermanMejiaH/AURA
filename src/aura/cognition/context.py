from __future__ import annotations

from dataclasses import dataclass, field

from ..container import DependencyContainer
from .working_memory import WorkingMemory


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

    def to_system_prompt(self) -> str:
        """Formats identity, background context, memory, and tools into a system prompt."""
        parts = [self.system_instruction]

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
            for turn in self.conversation_history[-6:]:
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
            history = working_memory.get_recent_conversation(limit=6)

        world_entities: list[str] = []
        relevant_memories: list[str] = []
        available_tools: list[dict[str, str]] = []

        if self.container is not None:
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
        )
