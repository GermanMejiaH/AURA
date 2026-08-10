from __future__ import annotations

from aura.cognition.memory_detector import ExplicitMemoryDetector


def test_explicit_memory_detector_unambiguous_patterns() -> None:
    text1 = "AURA, recuerda que estoy estudiando Ingeniería de Software"
    res1 = ExplicitMemoryDetector.detect(text1)
    assert res1.detected is True
    assert res1.predicate == "actividad"
    assert "estudiando ingeniería de software" in res1.object_val.lower()
    assert "recordaré" in res1.confirmation_response

    res2 = ExplicitMemoryDetector.detect("Guarda que mi color favorito es azul")
    assert res2.detected is True
    assert res2.predicate == "color_favorito"
    assert res2.object_val == "azul"

    res3 = ExplicitMemoryDetector.detect("No olvides que mi moto es una DT 125")
    assert res3.detected is True
    assert res3.predicate == "moto"
    assert "dt 125" in res3.object_val.lower()


def test_explicit_memory_detector_rejects_ambiguous_statements() -> None:
    # Casual/ambiguous statements should NOT trigger automatic explicit memory storage
    res1 = ExplicitMemoryDetector.detect("El cielo está despejado hoy")
    assert res1.detected is False

    res2 = ExplicitMemoryDetector.detect("Me gusta comer pizza")
    assert res2.detected is False

    res3 = ExplicitMemoryDetector.detect("Mi computadora es rápida")
    assert res3.detected is False
