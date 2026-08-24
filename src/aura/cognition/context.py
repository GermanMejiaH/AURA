from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .conversation_context import ConversationContext
from .working_memory import WorkingMemory

if TYPE_CHECKING:
    from ..container import DependencyContainer
    from ..memory.models import Episode
    from .goals import PrioritizedGoal
    from .identity import AURAIdentity
    from .intent import Intent
    from .session import SessionContext


def estimate_tokens(text: str) -> int:
    """Estimates BPE tokens using tiktoken if available, or accurate BPE character density ratio."""
    if not text:
        return 0
    try:
        import tiktoken  # type: ignore[import-not-found]

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        # Realistic BPE ratio for Spanish text & markdown syntax (~3.2 chars/token)
        return max(1, int(len(text) / 3.2))


def get_max_history_turns(intent: Any | None, input_text: str = "") -> int:
    """Calculates adaptive conversation history window based on intent and input text."""
    intent_type_str = ""
    if intent is not None:
        intent_type = getattr(intent, "intent_type", intent)
        intent_type_str = (
            intent_type.value if hasattr(intent_type, "value") else str(intent_type or "")
        ).upper()

    input_lower = input_text.lower().strip()
    casual_greetings = (
        "hola",
        "hola aura",
        "saludos",
        "buenos días",
        "buenas noches",
        "buenas tardes",
        "gracias",
        "de nada",
        "cómo estás",
        "como estas",
        "hey",
        "hi",
        "hello",
    )

    if any(
        kw in input_lower
        for kw in (
            "resumir",
            "resumen",
            "recap",
            "summary",
            "historial",
            "anterior",
            "conversación",
        )
    ):
        return 12

    if input_lower in casual_greetings or intent_type_str in (
        "GREET",
        "GREETING",
        "SALUTATION",
        "SMALLTALK",
    ):
        return 2
    elif intent_type_str in ("QUESTION", "INFORMATIONAL", "CONFIRMATION", "CANCELLATION"):
        return 6
    elif intent_type_str in ("TASK_REQUEST", "PLAN", "GOAL", "COMMAND", "AUTONOMY", "ACTION"):
        return 8
    elif intent_type_str in (
        "REFLECT",
        "LEARN",
        "MEMORY_QUERY",
        "AUTOBIOGRAPHICAL",
        "MEMORY_UPDATE",
    ):
        return 12
    return 4


@dataclass
class CognitiveContext:
    """Encapsulates structured cognitive context compiled for LLM reasoning."""

    system_instruction: str
    user_input: str
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    working_memory_summary: str = ""
    world_entities: list[str] = field(default_factory=list)
    relevant_memories: list[str] = field(default_factory=list)
    relevant_episodes: list[Episode] = field(default_factory=list)
    prioritized_goals: list[PrioritizedGoal] = field(default_factory=list)
    available_tools: list[dict[str, str]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    identity: AURAIdentity | None = None
    session_context: SessionContext | None = None
    conversation_context: ConversationContext | None = None
    intent: Any | None = None

    def to_system_prompt(self) -> str:
        """Formats identity, background context, memory, tools, and results into prompt."""
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
            if self.session_context.task_detail:
                sess_info.append(f"Detalle Tarea: {self.session_context.task_detail}")
            if self.session_context.active_entity:
                sess_info.append(f"Entidad Activa: {self.session_context.active_entity}")
            if self.session_context.last_intent:
                sess_info.append(f"Intención reciente: {self.session_context.last_intent}")
            if sess_info:
                parts.append(f"[ESTADO CONTEXTUAL DE SESIÓN]: {', '.join(sess_info)}")

        if self.conversation_context is not None:
            anaphora = self.conversation_context.anaphora_resolution
            if anaphora and anaphora.requires_reference:
                if anaphora.is_ambiguous:
                    parts.append("[REFERENCIA ACTIVA]: AMBIGUA — SE REQUIERE ACLARACIÓN")
                elif anaphora.resolved_entity:
                    parts.append(f"[REFERENCIA ACTIVA]: {anaphora.resolved_entity}")

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

        if self.relevant_episodes:
            parts.append("\n[EXPERIENCIAS EPISÓDICAS PASADAS RELEVANTES]:")
            for ep in self.relevant_episodes[:3]:
                clean_summary = ep.summary.replace(
                    "</retrieved_memory>", "[/retrieved_memory_escaped]"
                ).replace("<retrieved_memory>", "[retrieved_memory_escaped]")
                parts.append(f"  • [episodio {ep.id}]: {clean_summary}")
                try:
                    import json

                    details = json.loads(ep.details) if ep.details else {}
                    lesson = details.get("lesson_learned")
                    if lesson:
                        clean_lesson = (
                            str(lesson)
                            .replace("</retrieved_memory>", "[/retrieved_memory_escaped]")
                            .replace("<retrieved_memory>", "[retrieved_memory_escaped]")
                        )
                        parts.append(f"    - Lección aprendida: {clean_lesson}")
                except Exception:
                    pass

        if self.prioritized_goals:
            parts.append("\n[OBJETIVOS PERSISTENTES PRIORIZADOS]:")
            for pg in self.prioritized_goals[:5]:
                clean_desc = pg.goal.description.replace(
                    "</retrieved_memory>", "[/retrieved_memory_escaped]"
                ).replace("<retrieved_memory>", "[retrieved_memory_escaped]")
                parts.append(
                    f"  • [#{pg.rank} Score {pg.score:.1f}] "
                    f"({pg.goal.goal_id} - {pg.goal.status.value}): "
                    f'"{clean_desc}" ({pg.explanation})'
                )

        if self.tool_results:
            parts.append(
                "\n[RESULTADOS DE HERRAMIENTAS RECIENTES]: "
                "Los siguientes datos provienen de herramientas ejecutadas realmente. "
                "DEBES responder utilizando estos resultados de forma directa y verídica:"
            )
            for tres in self.tool_results:
                name = tres.get("tool_name", "tool")
                output = tres.get("output", "")
                err = tres.get("error")
                if err:
                    parts.append(f"  • Herramienta '{name}': Fallo ({err})")
                else:
                    parts.append(f"  • Herramienta '{name}': {output}")

        return "\n".join(parts)

    def to_formatted_prompt(self) -> str:
        """Formats conversational history and current input for LLM prompt."""
        parts: list[str] = []

        history_source = (
            self.conversation_context.relevant_turns
            if (self.conversation_context and self.conversation_context.relevant_turns)
            else self.conversation_history
        )

        if history_source:
            max_h_turns = get_max_history_turns(self.intent, self.user_input)
            parts.append("Historial conversacional reciente:")
            for turn in history_source[-max_h_turns:]:
                role = "Usuario" if turn.get("role") == "user" else "AURA"
                parts.append(f"  [{role}]: {turn.get('content', '')}")
            parts.append("")

        parts.append(f"Usuario: {self.user_input}")
        return "\n".join(parts)

    def get_total_prompt_tokens(self) -> int:
        """Calculates final total prompt token count across system prompt
        and formatted user prompt."""
        sys_p = self.to_system_prompt()
        fmt_p = self.to_formatted_prompt()
        return estimate_tokens(sys_p + fmt_p)


class CognitiveContextBuilder:
    """Compiles structured CognitiveContext from container modules."""

    DEFAULT_INSTRUCTION = (
        "Eres AURA (Adaptive Unified Reasoning Assistant), un asistente cognitivo inteligente y "
        "autónomo. Respondes siempre en español de forma natural, concisa y directa por voz "
        "(máximo 1 a 3 oraciones breves). "
        "Si el usuario realiza una interacción casual (como 'Gracias' o 'Hola'), responde "
        "de forma cálida, amigable y muy breve (1 oración directa), sin discursos de plantilla. "
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
        conversation_context: ConversationContext | None = None,
        intent: Intent | None = None,
    ) -> CognitiveContext:
        instruction = system_instruction or self.DEFAULT_INSTRUCTION

        history: list[dict[str, str]] = []
        if working_memory is not None:
            history = working_memory.get_recent_conversation(limit=12)

        world_entities: list[str] = []
        relevant_memories: list[str] = []
        relevant_episodes: list[Episode] = []
        prioritized_goals: list[PrioritizedGoal] = []
        available_tools: list[dict[str, str]] = []
        identity_obj = None
        session_obj = None

        detected_intent = intent

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

        if detected_intent is None and self.container is not None:
            try:
                from .intent import IntentDetector

                if self.container.has(IntentDetector):
                    detected_intent = self.container.resolve(IntentDetector).detect(input_text)
            except Exception:
                pass

        if detected_intent is None:
            try:
                from .intent import IntentDetector

                detected_intent = IntentDetector.detect(input_text)
            except Exception:
                pass

        if self.container is not None:
            try:
                from .intent import IntentDetector

                intent_type = detected_intent.intent_type if detected_intent else None
                intent_name = (
                    intent_type.value
                    if (intent_type and hasattr(intent_type, "value"))
                    else str(intent_type or "")
                ).upper()
                input_lower = input_text.lower().strip()

                casual_greetings = (
                    "hola",
                    "hola aura",
                    "saludos",
                    "buenos días",
                    "buenas noches",
                    "buenas tardes",
                    "gracias",
                    "de nada",
                    "cómo estás",
                    "como estas",
                    "hey",
                    "hi",
                    "hello",
                )
                is_casual = input_lower in casual_greetings or intent_name in (
                    "GREET",
                    "SALUTATION",
                    "SMALLTALK",
                )

                # 1. Pull CWM entities if non-casual or explicitly relevant
                if not is_casual:
                    from ..world import CognitiveWorldModel

                    if self.container.has(CognitiveWorldModel):
                        cwm = self.container.resolve(CognitiveWorldModel)
                        world_entities = [
                            f"{e.name} ({getattr(e.type, 'value', str(e.type))})"
                            for e in cwm.all_entities()
                        ]

                # 2. Pull Persistent Memory facts/preferences if intent requires it
                if detected_intent and IntentDetector.should_query_persistent_memory(
                    detected_intent, input_text
                ):
                    from ..memory import MemoryModule

                    if self.container.has(MemoryModule):
                        mem = self.container.resolve(MemoryModule)
                        retrieval = mem.retrieval.query(input_text)
                        relevant_memories = [
                            f"[{f.predicate} del {f.subject}]: {f.object_val}"
                            for f in retrieval.facts
                        ] + [f"[{p.key}]: {p.value}" for p in retrieval.preferences]

                # 3. Pull Episodic Experiences if non-casual
                if not is_casual:
                    from ..memory import CognitiveContextManager

                    if self.container.has(CognitiveContextManager):
                        cog_ctx_mgr = self.container.resolve(CognitiveContextManager)
                        relevant_episodes = cog_ctx_mgr.get_relevant_episodes(
                            query=input_text,
                            intent_type=intent_name,
                            limit=3,
                        )

                tool_intents = (
                    "TASK_REQUEST",
                    "COMMAND",
                    "ACTION",
                    "TOOL_USE",
                    "PLAN",
                    "GOAL",
                    "INFORMATION_REQUEST",
                )
                tool_keywords = (
                    "alarma",
                    "temporizador",
                    "timer",
                    "recordatorio",
                    "notificación",
                    "notificacion",
                    "buscar",
                    "búscame",
                    "buscame",
                    "search",
                    "clima",
                    "tiempo",
                    "ejecutar",
                    "comando",
                    "sistema",
                    "archivos",
                    "apagar",
                    "prender",
                    "crear plan",
                )
                requires_tools = intent_name in tool_intents or any(
                    kw in input_lower for kw in tool_keywords
                )

                # 4. Pull Tools metadata ONLY if input/intent requires tool orchestration
                if requires_tools:
                    from ..tools import ToolRegistry

                    if self.container.has(ToolRegistry):
                        reg = self.container.resolve(ToolRegistry)
                        available_tools = [
                            {"name": meta.name, "description": meta.description}
                            for meta in reg.list_metadata()
                        ]

                # 5. Pull PersistentGoals if non-casual
                if not is_casual:
                    from .goals import GoalManager, GoalPrioritizer

                    if self.container.has(GoalManager):
                        goal_mgr = self.container.resolve(GoalManager)
                        all_goals = goal_mgr.list_goals()
                        if all_goals:
                            prioritizer = GoalPrioritizer()
                            prioritized_goals = prioritizer.prioritize(all_goals)

            except Exception:
                pass

        ctx_obj = CognitiveContext(
            system_instruction=instruction,
            user_input=input_text,
            conversation_history=history,
            world_entities=world_entities,
            relevant_memories=relevant_memories,
            relevant_episodes=relevant_episodes,
            prioritized_goals=prioritized_goals,
            available_tools=available_tools,
            identity=identity_obj,
            session_context=session_obj,
            conversation_context=conversation_context,
            intent=detected_intent,
        )

        try:
            from ..logging import get_logger

            b_logger = get_logger("CognitiveContextBuilder")
            max_h = get_max_history_turns(detected_intent, input_text)
            hist_src = (
                conversation_context.relevant_turns
                if (conversation_context and conversation_context.relevant_turns)
                else history
            )
            sel_hist = hist_src[-max_h:] if hist_src else []
            h_turns = len(sel_hist)
            h_text = " ".join(str(t.get("content", "")) for t in sel_hist)
            h_tokens = estimate_tokens(h_text)
            mem_text = " ".join(relevant_memories)
            mem_tokens = estimate_tokens(mem_text)
            ep_text = " ".join(getattr(ep, "summary", "") for ep in relevant_episodes)
            ep_tokens = estimate_tokens(ep_text)
            goal_text = " ".join(getattr(pg.goal, "description", "") for pg in prioritized_goals)
            goal_tokens = estimate_tokens(goal_text)
            tool_text = " ".join(
                t.get("name", "") + " " + t.get("description", "") for t in available_tools
            )
            tool_tokens = estimate_tokens(tool_text)

            sys_p = ctx_obj.to_system_prompt()
            fmt_p = ctx_obj.to_formatted_prompt()
            tot_p_tokens = estimate_tokens(sys_p + fmt_p)

            b_logger.info(
                f"[CONTEXT BUILD] history_turns={h_turns} history_tokens={h_tokens} "
                f"memory_tokens={mem_tokens} episode_tokens={ep_tokens} "
                f"goal_tokens={goal_tokens} tool_tokens={tool_tokens} "
                f"total_prompt_tokens={tot_p_tokens}"
            )
        except Exception:
            pass

        return ctx_obj
