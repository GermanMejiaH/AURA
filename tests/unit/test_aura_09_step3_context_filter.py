from __future__ import annotations

import copy

from aura.cognition import (
    AnaphoraResolution,
    ConversationContextFilter,
    WorkingMemory,
)


def test_case_1_simple_continuity() -> None:
    history = [
        {"role": "user", "content": "Hablemos de motos"},
        {"role": "assistant", "content": "Claro, ¿qué tipo de motos te interesan?"},
        {"role": "user", "content": "Tengo una DT 125"},
        {"role": "assistant", "content": "Es una moto legendaria de dos tiempos."},
        {"role": "user", "content": "¿Qué carburador me recomiendas?"},
        {"role": "assistant", "content": "Un Mikuni 28mm es una excelente opción."},
        {"role": "user", "content": "¿Y qué escape?"},
        {"role": "assistant", "content": "Un escape de expansión es ideal."},
        {"role": "user", "content": "¿Cuál de esos dos es mejor?"},
    ]

    filtered = ConversationContextFilter.filter_turns(
        history=history,
        current_topic="motos",
        max_turns=8,
    )

    assert len(filtered) <= 8
    # Chronological order check
    indices = [history.index(t) for t in filtered]
    assert indices == sorted(indices)
    assert any("carburador" in t["content"] for t in filtered)


def test_case_2_topic_change() -> None:
    history = [
        {"role": "user", "content": "Hablemos de motos"},
        {"role": "user", "content": "Tengo una DT 125"},
        {"role": "user", "content": "¿Qué carburador me recomiendas?"},
        {"role": "user", "content": "Ahora quiero hablar de mi PC"},
        {"role": "assistant", "content": "De acuerdo, cuéntame sobre tu PC."},
        {"role": "user", "content": "Tengo una GTX 1650"},
        {"role": "user", "content": "¿Qué GPU me recomiendas?"},
    ]

    filtered = ConversationContextFilter.filter_turns(
        history=history,
        current_topic="PC",
        active_task="recomendación",
        task_detail="GPU",
        max_turns=8,
    )

    assert len(filtered) <= 8
    # PC/GPU turns must be included and prioritized by recency + topic
    contents = [t["content"] for t in filtered]
    assert "¿Qué GPU me recomiendas?" in contents
    assert "Tengo una GTX 1650" in contents


def test_case_3_active_entity() -> None:
    history = [
        {"role": "user", "content": "Estoy mirando tarjetas gráficas"},
        {"role": "user", "content": "Tengo una GTX 1650"},
        {"role": "assistant", "content": "Es una tarjeta básica de entrada."},
        {"role": "user", "content": "También estoy considerando una RTX 3060"},
        {"role": "assistant", "content": "La RTX 3060 tiene 12GB de VRAM."},
    ]

    filtered = ConversationContextFilter.filter_turns(
        history=history,
        current_topic="tarjetas gráficas",
        active_entity="RTX 3060",
        max_turns=8,
    )

    assert len(filtered) <= 8
    # RTX 3060 turn must be included
    assert any("RTX 3060" in t["content"] for t in filtered)


def test_case_4_active_task() -> None:
    history = [
        {"role": "user", "content": "Hola"},
        {"role": "user", "content": "Quiero armar mi equipo informático"},
        {"role": "user", "content": "Necesito una buena recomendación de GPU para mi PC"},
        {"role": "assistant", "content": "Te sugiero mirar modelos con al menos 8GB VRAM."},
    ]

    filtered = ConversationContextFilter.filter_turns(
        history=history,
        current_topic="PC",
        active_task="recomendación",
        task_detail="GPU",
        max_turns=8,
    )

    assert len(filtered) <= 8
    assert any("GPU" in t["content"] for t in filtered)


def test_case_5_long_history_max_8_limit_and_chronology() -> None:
    # 14 turns
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Turno {i}"} for i in range(14)
    ]

    filtered = ConversationContextFilter.filter_turns(
        history=history,
        max_turns=8,
    )

    assert len(filtered) == 8
    # Verify strict original chronological order
    indices = [history.index(t) for t in filtered]
    assert indices == sorted(indices)


def test_case_6_empty_or_no_matching_context() -> None:
    # Empty history
    assert ConversationContextFilter.filter_turns(history=[], max_turns=8) == []

    # History with no topic match
    history = [{"role": "user", "content": f"Turno aleatorio {i}"} for i in range(5)]
    filtered = ConversationContextFilter.filter_turns(
        history=history, current_topic="astrofísica", max_turns=8
    )
    assert len(filtered) == 5
    assert [t["content"] for t in filtered] == [f"Turno aleatorio {i}" for i in range(5)]


def test_case_7_ambiguous_reference_no_hallucinated_filter() -> None:
    history = [
        {"role": "user", "content": "Veo una moto y un auto"},
        {"role": "user", "content": "¿Cuál me recomiendas?"},
    ]

    ambiguous_res = AnaphoraResolution(
        resolved_entity=None,
        is_ambiguous=True,
        candidate_entities=["moto", "auto"],
        requires_reference=True,
    )

    filtered = ConversationContextFilter.filter_turns(
        history=history,
        anaphora_resolution=ambiguous_res,
        max_turns=8,
    )

    # Filter must not force resolve an ambiguity entity target
    assert len(filtered) == 2


def test_case_8_no_mutation_of_working_memory() -> None:
    wm = WorkingMemory()
    for i in range(10):
        wm.add_conversation_turn("user" if i % 2 == 0 else "assistant", f"Mensaje {i}")

    original_history = wm.get_recent_conversation()
    copied_history = copy.deepcopy(original_history)

    _ = ConversationContextFilter.filter_turns(
        history=original_history,
        current_topic="Prueba",
        max_turns=8,
    )

    # Original working memory history must be 100% identical and unmutated
    assert wm.get_recent_conversation() == copied_history
