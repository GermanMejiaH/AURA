from __future__ import annotations

from aura.cognition import AnaphoraResolver, SessionManager


def test_anaphora_resolver_unique_reference() -> None:
    # 1 single recent entity -> resolves deterministically
    res = AnaphoraResolver.analyze("¿Cuál me recomiendas?", recent_entities=["Yamaha MT-07"])
    assert res.requires_reference is True
    assert res.is_ambiguous is False
    assert res.resolved_entity == "Yamaha MT-07"


def test_anaphora_resolver_ambiguous_reference() -> None:
    # 2 or more candidates -> flag as ambiguous! DO NOT pick arbitrarily!
    res = AnaphoraResolver.analyze(
        "¿Cuál me recomiendas?", recent_entities=["Yamaha MT-07", "Honda CB650R"]
    )
    assert res.requires_reference is True
    assert res.is_ambiguous is True
    assert res.resolved_entity is None
    assert len(res.candidate_entities) == 2


def test_anaphora_resolver_absence_of_reference() -> None:
    # Standard sentence without anaphoric triggers
    res = AnaphoraResolver.analyze("Hola, me llamo Andrés")
    assert res.requires_reference is False
    assert res.resolved_entity is None
    assert res.is_ambiguous is False


def test_anaphora_resolver_fallback_to_topic_or_active_entity() -> None:
    # No candidate list, but active_topic or active_entity exists
    res = AnaphoraResolver.analyze("¿Dónde la puedo comprar?", active_topic="motos")
    assert res.requires_reference is True
    assert res.is_ambiguous is False
    assert res.resolved_entity == "motos"


def test_session_context_topic_management() -> None:
    sm = SessionManager()

    # Topic retention & setting
    sm.set_topic("motos")
    assert sm.get_context().current_topic == "motos"

    # Topic change
    sm.set_topic("tarjeta gráfica PC")
    assert sm.get_context().current_topic == "tarjeta gráfica PC"

    # Topic clearing
    sm.clear_topic()
    assert sm.get_context().current_topic is None


def test_session_context_task_detail_and_active_entity() -> None:
    sm = SessionManager()

    # Task and task_detail
    sm.set_task("configurar PC", detail="revisar RAM")
    ctx = sm.get_context()
    assert ctx.active_task == "configurar PC"
    assert ctx.task_detail == "revisar RAM"

    # Active entity
    sm.set_active_entity("Nvidia RTX 4070")
    assert sm.get_context().active_entity == "Nvidia RTX 4070"

    # Clear active entity & clear task
    sm.clear_active_entity()
    assert sm.get_context().active_entity is None

    sm.clear_task()
    assert sm.get_context().active_task is None
    assert sm.get_context().task_detail is None
