from __future__ import annotations

from aura.config import ConfigurationManager


def test_default_config_keys_exist():
    cfg = ConfigurationManager()
    assert cfg.has("system.name")
    assert cfg.has("system.version")
    assert cfg.has("logging.level")
    assert cfg.has("event_bus.max_history")
    assert cfg.has("health.check_interval_sec")
    assert cfg.has("core.boot_timeout_sec")


def test_config_get_default():
    cfg = ConfigurationManager()
    assert cfg.get("system.name") == "AURA"
    assert cfg.get("logging.level") == "INFO"
    assert cfg.get("event_bus.max_history") == 1000


def test_config_get_with_fallback_default():
    cfg = ConfigurationManager()
    assert cfg.get("non.existent.key", 42) == 42
    assert cfg.get("another.unknown", None) is None


def test_config_get_typed():
    cfg = ConfigurationManager()
    assert cfg.get_typed("health.check_interval_sec", int, 0) == 30
    assert cfg.get_typed("health.enabled", bool, False) is True
    assert cfg.get_typed("unknown", int, 7) == 7


def test_config_set_overrides_value():
    cfg = ConfigurationManager()
    cfg.set("system.name", "AURA-TEST", source="unittest")
    assert cfg.get("system.name") == "AURA-TEST"


def test_config_load_from_dict_nested_flattens_keys():
    cfg = ConfigurationManager()
    cfg.load_from_dict(
        {"system": {"environment": "testing", "timezone": "America/New_York"}},
        source="dict",
    )
    assert cfg.get("system.environment") == "testing"
    assert cfg.get("system.timezone") == "America/New_York"


def test_config_load_from_env_uses_prefix(monkeypatch):
    monkeypatch.setenv("AURA_LOGGING__LEVEL", "DEBUG")
    monkeypatch.setenv("AURA_EVENT_BUS__MAX_HISTORY", "500")
    cfg = ConfigurationManager()
    cfg.load_from_env(prefix="AURA_")
    assert cfg.get("logging.level") == "DEBUG"
    assert cfg.get("event_bus.max_history") == 500


def test_config_coerce_env_values(monkeypatch):
    monkeypatch.setenv("AURA_HEALTH__ENABLED", "false")
    monkeypatch.setenv("AURA_CORE__BOOT_TIMEOUT_SEC", "99")
    cfg = ConfigurationManager()
    cfg.load_from_env(prefix="AURA_")
    assert cfg.get("health.enabled") is False
    assert cfg.get("core.boot_timeout_sec") == 99


def test_config_sources_tracking():
    cfg = ConfigurationManager()
    cfg.load_from_dict({"a": {"b": 1}}, source="dict-test")
    assert "dict-test" in cfg.sources()


def test_config_mark_loaded():
    cfg = ConfigurationManager()
    assert not cfg.is_loaded
    cfg.mark_loaded()
    assert cfg.is_loaded


def test_config_keys_sorted():
    cfg = ConfigurationManager()
    keys = cfg.keys()
    assert keys == sorted(keys)
    assert len(keys) > 10


def test_config_as_dict_matches():
    cfg = ConfigurationManager()
    d = cfg.as_dict()
    assert d["system.name"] == "AURA"
    assert len(d) == len(cfg.keys())
