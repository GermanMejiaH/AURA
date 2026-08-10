from __future__ import annotations

from aura.cognition import AURAIdentity, IdentityManager
from aura.config import ConfigurationManager


def test_aura_identity_defaults() -> None:
    identity = AURAIdentity()
    assert identity.name == "AURA"
    assert "empatía" in identity.mission
    assert identity.language == "es"
    assert len(identity.behavior_rules) > 0
    assert len(identity.limitations) > 0


def test_identity_manager_customization() -> None:
    mgr = IdentityManager()
    custom = mgr.update_identity(
        name="AURA Pro",
        personality_style="conciso, técnico y formal",
    )

    assert custom.name == "AURA Pro"
    assert custom.personality_style == "conciso, técnico y formal"

    current = mgr.get_identity()
    assert current.name == "AURA Pro"


def test_identity_manager_load_from_config() -> None:
    cfg = ConfigurationManager()
    cfg.set("identity.name", "AURA Core")
    cfg.set("identity.personality_style", "amigable y enfocado en código")

    mgr = IdentityManager(config=cfg)
    identity = mgr.get_identity()

    assert identity.name == "AURA Core"
    assert identity.personality_style == "amigable y enfocado en código"
