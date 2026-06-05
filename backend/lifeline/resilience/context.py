"""Run identity for resilience recording.

ToolGateway / ResilientLLM live in Deps (built once), but the run/thread id is
per-invocation. AgentRunner sets it via run_scope() so the recorders can tag
events to the current run without threading run_id through every node.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_current_run: ContextVar[str | None] = ContextVar("current_run", default=None)


def get_run() -> str | None:
    return _current_run.get()


def set_run(run_id: str | None):
    """Set the current run; returns the token (use _current_run.reset(token))."""
    return _current_run.set(run_id)


@contextmanager
def run_scope(run_id: str | None):
    token = _current_run.set(run_id)
    try:
        yield
    finally:
        try:
            _current_run.reset(token)
        except ValueError:
            # Streaming responses advance the generator in a different Context, so
            # the token can't be reset there; clear the value instead.
            _current_run.set(None)
