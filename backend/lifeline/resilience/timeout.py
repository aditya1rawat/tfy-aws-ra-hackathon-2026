"""Per-call wall-clock timeout for blocking LLM/tool calls.

Runs the call on a worker thread and waits at most cutoff_s. A real overrun
raises CallTimeout (the caller maps it to the layer's transient failure). This
is separate from the chaos `timeout` mode, which raises directly without waiting.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FTimeout
from typing import Callable, TypeVar

T = TypeVar("T")


class CallTimeout(Exception):
    """A wrapped call exceeded its cutoff."""


def call_with_timeout(fn: Callable[[], T], *, cutoff_s: float) -> T:
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        try:
            return fut.result(timeout=cutoff_s)
        except _FTimeout:
            raise CallTimeout(f"call exceeded {cutoff_s}s")
