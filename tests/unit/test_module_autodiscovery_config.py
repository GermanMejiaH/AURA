from __future__ import annotations

from aura.config import ConfigurationManager
from aura.core.aura import AURA, AURABootOptions


def test_autodiscovery_default_is_false():
    config = ConfigurationManager()
    assert config.get("modules.auto_discover") is False

    options = AURABootOptions()
    assert options.auto_discover_modules is False


def test_autodiscovery_explicit_true():
    options = AURABootOptions(auto_discover_modules=True)
    aura = AURA(options=options)
    aura.boot()
    assert aura.options.auto_discover_modules is True
    aura.shutdown()


def test_autodiscovery_explicit_false():
    options = AURABootOptions(auto_discover_modules=False)
    aura = AURA(options=options)
    aura.boot()
    assert aura.options.auto_discover_modules is False
    aura.shutdown()
