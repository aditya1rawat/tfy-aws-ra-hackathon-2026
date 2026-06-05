import importlib

import dotenv

import lifeline.config as config


def test_database_url_defaults_empty(monkeypatch):
    # Don't let the developer's .env repopulate the var on reload.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(config)
    assert config.get_settings().database_url == ""


def test_database_url_from_env(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    importlib.reload(config)
    assert config.get_settings().database_url == "postgresql://u:p@h/db"
