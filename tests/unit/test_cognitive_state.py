from __future__ import annotations

from aura.cognition import CognitiveState, CognitiveStateMachine


def test_cognitive_state_machine_transitions():
    sm = CognitiveStateMachine()
    assert sm.state == CognitiveState.BOOTING

    sm.transition_to(CognitiveState.IDLE, reason="boot_complete")
    assert sm.state == CognitiveState.IDLE

    sm.transition_to(CognitiveState.THINKING, reason="user_query")
    assert sm.state == CognitiveState.THINKING

    history = sm.history()
    assert len(history) == 2
    assert history[0] == (CognitiveState.BOOTING, CognitiveState.IDLE, "boot_complete")
    assert history[1] == (CognitiveState.IDLE, CognitiveState.THINKING, "user_query")
