from __future__ import annotations

from aura.core.aura import AURA, AURABootOptions


def test_aura_shutdown_idempotent_before_boot():
    aura = AURA()
    assert aura.shutdown() is True
    assert aura.shutdown(wait=True, timeout=1.0) is True


def test_aura_shutdown_after_boot():
    aura = AURA(options=AURABootOptions(auto_discover_modules=False))
    aura.boot()
    assert aura.is_booted is True

    result = aura.shutdown(wait=True, timeout=2.0)
    assert result is True
    assert aura.is_booted is False
    assert aura.lifecycle.is_stopped is True

    # Repeated shutdown should be safe and idempotent
    assert aura.shutdown() is True
