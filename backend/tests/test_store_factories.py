from types import SimpleNamespace

from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.batch.store import JobStore
from lifeline.bridge.request_store import RequestStore
from lifeline.bridge.stores import make_checkpointer, make_job_store, make_request_store


def _settings(database_url=""):
    return SimpleNamespace(database_url=database_url, checkpoint_db_path=":memory:")


def test_no_dsn_uses_sqlite_jobstore():
    assert isinstance(make_job_store(_settings()), JobStore)


def test_no_dsn_uses_in_memory_request_store():
    assert isinstance(make_request_store(_settings()), RequestStore)


def test_no_dsn_uses_sqlite_checkpointer():
    cp = make_checkpointer(_settings())
    assert isinstance(cp, SqliteSaver)


def test_postgres_dsn_selects_pg_jobstore(monkeypatch):
    captured = {}

    class _FakePG:
        def __init__(self, dsn):
            captured["dsn"] = dsn

    monkeypatch.setattr("lifeline.bridge.stores.PostgresJobStore", _FakePG)
    out = make_job_store(_settings("postgresql://x"))
    assert isinstance(out, _FakePG)
    assert captured["dsn"] == "postgresql://x"
