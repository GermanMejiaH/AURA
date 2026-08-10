from __future__ import annotations

from aura.cognition.memory_detector import ExplicitMemoryDetector


def test_explicit_memory_detector_positive_cases() -> None:
    # 1. "Ahora, recuerda que mi color favorito es el rojo."
    res1 = ExplicitMemoryDetector.detect("Ahora, recuerda que mi color favorito es el rojo.")
    assert res1.detected is True
    assert res1.predicate == "color_favorito"
    assert "rojo" in res1.object_val.lower()

    # 2. "Bueno AURA, guarda que mi moto es una DT."
    res2 = ExplicitMemoryDetector.detect("Bueno AURA, guarda que mi moto es una DT.")
    assert res2.detected is True
    assert res2.predicate == "moto"
    assert "dt" in res2.object_val.lower()

    # 3. "Por favor recuerda que mi correo es test@aura.com."
    res3 = ExplicitMemoryDetector.detect("Por favor recuerda que mi correo es test@aura.com.")
    assert res3.detected is True
    assert res3.predicate == "correo"
    assert "test@aura.com" in res3.object_val

    # 4. "Oye AURA, recuerda que mi cumpleaños es el 2 de agosto."
    res4 = ExplicitMemoryDetector.detect("Oye AURA, recuerda que mi cumpleaños es el 2 de agosto.")
    assert res4.detected is True
    assert res4.predicate == "cumpleaños"
    assert "2 de agosto" in res4.object_val

    # 5. "Quiero que recuerdes que estudio ingeniería de software."
    res5 = ExplicitMemoryDetector.detect("Quiero que recuerdes que estudio ingeniería de software.")
    assert res5.detected is True
    assert res5.predicate == "actividad"
    assert "ingeniería de software" in res5.object_val.lower()


def test_explicit_memory_detector_temporal_adverb_normalization() -> None:
    # "Ahora mi comida favorita es la hamburguesa"
    r1 = ExplicitMemoryDetector.detect("Ahora mi comida favorita es la hamburguesa")
    assert r1.detected is True
    assert r1.predicate == "comida_favorita"
    assert "hamburguesa" in r1.object_val.lower()

    # "Recuerda que ahora mi comida favorita es la hamburguesa"
    r2 = ExplicitMemoryDetector.detect("Recuerda que ahora mi comida favorita es la hamburguesa")
    assert r2.detected is True
    assert r2.predicate == "comida_favorita"

    # "Guarda que mi comida favorita ahora es la hamburguesa"
    r3 = ExplicitMemoryDetector.detect("Guarda que mi comida favorita ahora es la hamburguesa")
    assert r3.detected is True
    assert r3.predicate == "comida_favorita"

    # "AURA, recuerda que actualmente mi comida favorita es la hamburguesa"
    r4 = ExplicitMemoryDetector.detect(
        "AURA, recuerda que actualmente mi comida favorita es la hamburguesa"
    )
    assert r4.detected is True
    assert r4.predicate == "comida_favorita"


def test_explicit_memory_detector_negative_cases() -> None:
    # 6. "No recuerdo que mi color favorito sea rojo."
    res6 = ExplicitMemoryDetector.detect("No recuerdo que mi color favorito sea rojo.")
    assert res6.detected is False

    # 7. "Recuerdo que mi color favorito es rojo."
    res7 = ExplicitMemoryDetector.detect("Recuerdo que mi color favorito es rojo.")
    assert res7.detected is False

    # 8. "¿Recuerdas cuál es mi color favorito?"
    res8 = ExplicitMemoryDetector.detect("¿Recuerdas cuál es mi color favorito?")
    assert res8.detected is False

    # 9. "AURA, ¿recuerdas mi cumpleaños?"
    res9 = ExplicitMemoryDetector.detect("AURA, ¿recuerdas mi cumpleaños?")
    assert res9.detected is False

    # 10. "Me gustaría saber si recuerdas mi cumpleaños."
    res10 = ExplicitMemoryDetector.detect("Me gustaría saber si recuerdas mi cumpleaños.")
    assert res10.detected is False
