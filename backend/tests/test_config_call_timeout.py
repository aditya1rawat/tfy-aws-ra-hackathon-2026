import importlib

import dotenv

import lifeline.config as config


def test_default_call_timeout(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("CALL_TIMEOUT_S", raising=False)
    importlib.reload(config)
    assert config.get_settings().call_timeout_s == 5.0


def test_call_timeout_from_env(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("CALL_TIMEOUT_S", "2.5")
    importlib.reload(config)
    assert config.get_settings().call_timeout_s == 2.5
