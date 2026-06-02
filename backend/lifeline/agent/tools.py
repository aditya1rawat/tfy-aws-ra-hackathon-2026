import time
from typing import Callable

from lifeline.chaos.controller import ToolFailure
from lifeline.mcp_servers import benefits, chart, formulary, insurer, pharmacy


class ToolUnavailable(Exception):
    """Raised when a tool keeps failing after the gateway's retries are exhausted."""


class InProcessBackend:
    """Call Plan 1 MCP-server functions directly (no network).

    The Plan 3 MCP-gateway HTTP backend implements the same `invoke` signature.
    """

    def __init__(self) -> None:
        self._registry: dict[tuple[str, str], Callable] = {
            ("chart", "get_patient_chart"): chart.get_patient_chart,
            ("chart", "get_med_history"): chart.get_med_history,
            ("formulary", "check_coverage"): formulary.check_coverage,
            ("formulary", "needs_prior_auth"): formulary.needs_prior_auth,
            ("insurer", "submit_prior_auth"): insurer.submit_prior_auth,
            ("insurer", "get_auth_status"): insurer.get_auth_status,
            ("insurer", "cancel_auth"): insurer.cancel_auth,
            ("benefits", "search_programs"): benefits.search_programs,
            ("benefits", "submit_application"): benefits.submit_application,
            ("pharmacy", "approve_refill"): pharmacy.approve_refill,
        }

    def invoke(self, server: str, tool: str, kwargs: dict):
        fn = self._registry[(server, tool)]  # KeyError on unknown tool (programmer error)
        return fn(**kwargs)


class ToolGateway:
    """Retry transient tool failures with backoff; degrade to ToolUnavailable when exhausted."""

    def __init__(self, backend, retries: int = 3, base_delay: float = 0.2,
                 sleep: Callable[[float], None] = time.sleep):
        self._backend = backend
        self._retries = retries
        self._base_delay = base_delay
        self._sleep = sleep

    def call(self, server: str, tool: str, **kwargs):
        last_err: Exception | None = None
        for attempt in range(self._retries):
            try:
                return self._backend.invoke(server, tool, kwargs)
            except ToolFailure as err:
                last_err = err
                if attempt < self._retries - 1:
                    self._sleep(self._base_delay * (2 ** attempt))
        raise ToolUnavailable(f"{server}.{tool} failed after {self._retries} attempts: {last_err}")
