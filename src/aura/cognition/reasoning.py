from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..world import CognitiveWorldModel, WorldQueryEngine
from .context import CognitiveContext
from .provider import LLMProvider, MockLLMProvider
from .working_memory import WorkingMemory


@dataclass
class ReasoningResult:
    summary: str
    intent: str
    confidence: float = 1.0
    relevant_entities: list[str] = field(default_factory=list)
    suggested_actions: list[dict[str, Any]] = field(default_factory=list)
    raw_reasoning: dict[str, Any] = field(default_factory=dict)


class ReasoningEngine:
    """Combines WorkingMemory context, CWM, and LLMProvider to reason about situation."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        working_memory: WorkingMemory | None = None,
        cwm: CognitiveWorldModel | None = None,
    ) -> None:
        self.llm_provider = llm_provider if llm_provider is not None else MockLLMProvider()
        self.working_memory = working_memory if working_memory is not None else WorkingMemory()
        self.cwm = cwm if cwm is not None else CognitiveWorldModel()
        self.query_engine = WorldQueryEngine(self.cwm)

    def analyze(
        self,
        input_text: str,
        cognitive_context: CognitiveContext | dict[str, Any] | None = None,
    ) -> ReasoningResult:
        # Check CWM entities for mention match
        relevant_entities: list[str] = []
        for entity in self.cwm.all_entities():
            if entity.name.lower() in input_text.lower():
                relevant_entities.append(entity.id)

        if isinstance(cognitive_context, CognitiveContext):
            system_prompt = cognitive_context.to_system_prompt()
            formatted_prompt = cognitive_context.to_formatted_prompt()

            llm_res = self.llm_provider.generate_response(
                prompt=formatted_prompt,
                system_instruction=system_prompt,
            )

            return ReasoningResult(
                summary=llm_res.content,
                intent="user_interaction",
                confidence=1.0,
                relevant_entities=relevant_entities,
                suggested_actions=[],
                raw_reasoning={"llm_response": llm_res.content, "tokens_used": llm_res.tokens_used},
            )

        context_dict: dict[str, Any] = {
            "active_goal": self.working_memory.active_goal,
            "recent_conversation": self.working_memory.get_recent_conversation(limit=5),
            "world_entities_count": self.cwm.entities_count,
        }
        if isinstance(cognitive_context, dict):
            context_dict.update(cognitive_context)

        prompt = f"Analyze input '{input_text}' given context: {context_dict}"
        structured = self.llm_provider.structured_reason(prompt=prompt, context=context_dict)

        return ReasoningResult(
            summary=structured.get("reasoning", "Reasoning completed successfully."),
            intent=structured.get("intent", "user_interaction"),
            confidence=float(structured.get("confidence", 1.0)),
            relevant_entities=relevant_entities,
            suggested_actions=structured.get("actions", []),
            raw_reasoning=structured,
        )
