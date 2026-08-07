from __future__ import annotations

from aura.cognition import (
    DecisionEngine,
    MockLLMProvider,
    ReasoningEngine,
    ReasoningResult,
)
from aura.world import CognitiveWorldModel, Entity, EntityType


def test_reasoning_engine_analysis_with_cwm_entities():
    cwm = CognitiveWorldModel()
    cwm.add_entity(Entity(name="Oficina", type=EntityType.LOCATION))
    llm = MockLLMProvider()

    re = ReasoningEngine(llm_provider=llm, cwm=cwm)
    result = re.analyze("¿Dónde está la Oficina?")

    assert isinstance(result, ReasoningResult)
    assert len(result.relevant_entities) == 1
    assert len(llm.calls) == 1


def test_decision_engine_policy_evaluation():
    de = DecisionEngine(min_confidence=0.6)

    high_conf = ReasoningResult(summary="High confidence", intent="greet", confidence=0.9)
    decision1 = de.evaluate(high_conf)
    assert decision1.approved is True

    low_conf = ReasoningResult(summary="Low confidence", intent="unknown", confidence=0.3)
    decision2 = de.evaluate(low_conf)
    assert decision2.approved is False
