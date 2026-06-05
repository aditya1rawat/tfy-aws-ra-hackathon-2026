from lifeline.resilience.context import get_run, run_scope, set_run


def test_default_is_none():
    assert get_run() is None


def test_set_and_get():
    from lifeline.resilience import context
    tok = set_run("r1")
    assert get_run() == "r1"
    context._current_run.reset(tok)
    assert get_run() is None


def test_run_scope_sets_and_resets():
    assert get_run() is None
    with run_scope("r42"):
        assert get_run() == "r42"
    assert get_run() is None


def test_run_scope_nesting_restores_previous():
    with run_scope("outer"):
        with run_scope("inner"):
            assert get_run() == "inner"
        assert get_run() == "outer"
