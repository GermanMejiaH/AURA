from __future__ import annotations

from aura.cognition import IntentDetector, SessionManager


def test_session_manager_lifecycle() -> None:
    mgr = SessionManager()
    ctx1 = mgr.get_context()

    assert ctx1.session_id.startswith("sess_")
    assert ctx1.turn_count == 0
    assert ctx1.current_topic is None

    mgr.record_turn()
    mgr.record_turn()
    assert mgr.get_context().turn_count == 2


def test_session_manager_intent_and_topic_update() -> None:
    mgr = SessionManager()

    intent = IntentDetector.detect("Busca el reporte de ventas")
    mgr.update_intent(intent)

    ctx = mgr.get_context()
    assert ctx.last_intent == "task_request"
    assert ctx.active_task is not None
    assert "busca" in ctx.active_task.lower()


def test_session_reset_generates_fresh_session() -> None:
    mgr = SessionManager()
    ctx_old = mgr.get_context()
    mgr.set_topic("Programación")
    mgr.record_turn()

    ctx_new = mgr.reset_session()
    assert ctx_new.session_id != ctx_old.session_id
    assert ctx_new.turn_count == 0
    assert ctx_new.current_topic is None
