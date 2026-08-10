from __future__ import annotations

from aura.cognition import IntentDetector, IntentType


def test_intent_detection_greeting() -> None:
    res = IntentDetector.detect("Hola AURA")
    assert res.intent_type == IntentType.GREETING


def test_intent_detection_farewell() -> None:
    res = IntentDetector.detect("Adiós AURA, hasta luego")
    assert res.intent_type == IntentType.FAREWELL


def test_intent_detection_question() -> None:
    res = IntentDetector.detect("¿Qué hora es?")
    assert res.intent_type == IntentType.QUESTION


def test_intent_detection_command() -> None:
    res = IntentDetector.detect("Apaga la luz del estudio")
    assert res.intent_type == IntentType.COMMAND


def test_intent_detection_memory_query() -> None:
    res = IntentDetector.detect("¿Cuál es mi comida favorita?")
    assert res.intent_type == IntentType.MEMORY_QUERY


def test_intent_detection_memory_update() -> None:
    res = IntentDetector.detect("Recuerda que mi comida favorita es la pizza")
    assert res.intent_type == IntentType.MEMORY_UPDATE


def test_intent_detection_task_request() -> None:
    res = IntentDetector.detect("Busca el reporte de ventas")
    assert res.intent_type == IntentType.TASK_REQUEST


def test_intent_detection_confirmation() -> None:
    res = IntentDetector.detect("Sí, hazlo de una vez")
    assert res.intent_type == IntentType.CONFIRMATION


def test_intent_detection_cancellation() -> None:
    res = IntentDetector.detect("Cancelar la operación")
    assert res.intent_type == IntentType.CANCELLATION


def test_intent_detection_casual_fallback() -> None:
    res = IntentDetector.detect("Hoy es un día bastante tranquilo y lluvioso")
    assert res.intent_type == IntentType.CASUAL_CONVERSATION
