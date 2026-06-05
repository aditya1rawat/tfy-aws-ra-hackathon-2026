from lifeline.resilience.log import ResilienceLog


def test_record_and_query_by_run():
    log = ResilienceLog()
    log.record("r1", layer="llm", target="sonnet", attempt=1, mode="ratelimit",
               backoff_ms=100, outcome="fail")
    log.record("r1", layer="llm", target="haiku", attempt=1, mode=None,
               backoff_ms=0, outcome="recovered", recovered_by="haiku")
    log.record("r2", layer="tool", target="chart.get_patient_chart", attempt=1,
               mode="timeout", backoff_ms=0, outcome="degraded")
    r1 = log.by_run("r1")
    assert len(r1) == 2
    assert r1[0]["outcome"] == "fail" and r1[0]["target"] == "sonnet"
    assert r1[1]["recovered_by"] == "haiku"
    assert [e["run_id"] for e in log.all()] == ["r1", "r1", "r2"]
    assert log.by_run("r2")[0]["outcome"] == "degraded"


def test_clear():
    log = ResilienceLog()
    log.record("r1", layer="tool", target="x.y", attempt=1, mode="fail",
               backoff_ms=0, outcome="degraded")
    log.clear()
    assert log.all() == []
