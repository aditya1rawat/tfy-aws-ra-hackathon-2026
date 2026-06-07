from lifeline.resilience.telemetry import TelemetryLog


def _row(tlog, run_id="r1", model="sonnet", total=30):
    tlog.record(run_id, model=model, prompt_tokens=20, completion_tokens=10,
                latency_ms=120, cost=0.004, request_id="req_1",
                trace_url="https://t/req_1")


def test_record_and_by_run():
    t = TelemetryLog()
    _row(t)
    rows = t.by_run("r1")
    assert len(rows) == 1
    assert rows[0]["model"] == "sonnet"
    assert rows[0]["prompt_tokens"] == 20
    assert rows[0]["trace_url"] == "https://t/req_1"


def test_by_run_isolates_runs():
    t = TelemetryLog()
    _row(t, run_id="r1")
    _row(t, run_id="r2")
    assert len(t.by_run("r1")) == 1
    assert len(t.by_run("r2")) == 1


def test_recent_returns_newest_first_capped():
    t = TelemetryLog()
    for i in range(5):
        t.record(f"r{i}", model="m", prompt_tokens=1, completion_tokens=1,
                 latency_ms=1, cost=None, request_id=None, trace_url=None)
    recent = t.recent(3)
    assert len(recent) == 3
    assert recent[0]["run_id"] == "r4"  # newest first


def test_clear():
    t = TelemetryLog()
    _row(t)
    t.clear()
    assert t.by_run("r1") == []
    assert t.recent(10) == []
