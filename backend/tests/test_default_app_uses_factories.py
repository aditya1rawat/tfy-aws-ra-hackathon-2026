from langgraph.checkpoint.memory import InMemorySaver

import lifeline.bridge.app as appmod


def test_default_app_builds_stores_via_factories(monkeypatch):
    calls = {}

    def _job(s):
        calls["job"] = True
        return appmod.JobStore(":memory:")

    def _req(s):
        calls["req"] = True
        return appmod.RequestStore()

    def _cp(s):
        calls["cp"] = True
        return InMemorySaver()

    monkeypatch.setattr(appmod, "make_job_store", _job)
    monkeypatch.setattr(appmod, "make_request_store", _req)
    monkeypatch.setattr(appmod, "make_checkpointer", _cp)
    appmod._default_app()
    assert {"job", "req", "cp"} <= calls.keys()
