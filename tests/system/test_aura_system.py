from __future__ import annotations

from aura import main as aura_main
from aura.core import AURA, SystemState


def test_root_aura_entrypoint_import():
    # Verify that importing root aura.py works without sys.path collision
    import aura

    assert hasattr(aura, "AURA")
    assert aura.AURA is AURA


def test_main_cli_execution(monkeypatch):
    executed = False

    def mock_run_until_shutdown(self, poll_interval=0.5):
        nonlocal executed
        executed = True
        assert self.state == SystemState.RUNNING

    monkeypatch.setattr(AURA, "run_until_shutdown", mock_run_until_shutdown)

    code = aura_main()
    assert code == 0
    assert executed is True
