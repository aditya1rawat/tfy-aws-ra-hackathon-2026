import asyncio
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
    """Retry transient tool failures with backoff; degrade to ToolUnavailable when exhausted.

    When an `audit` log is provided, records the final outcome of each call.
    """

    def __init__(self, backend, retries: int = 3, base_delay: float = 0.2,
                 sleep: Callable[[float], None] = time.sleep, audit=None):
        self._backend = backend
        self._retries = retries
        self._base_delay = base_delay
        self._sleep = sleep
        self._audit = audit

    def call(self, server: str, tool: str, **kwargs):
        last_err: Exception | None = None
        for attempt in range(self._retries):
            try:
                result = self._backend.invoke(server, tool, kwargs)
                if self._audit is not None:
                    self._audit.record(server, tool, True)
                return result
            except ToolFailure as err:
                last_err = err
                if attempt < self._retries - 1:
                    self._sleep(self._base_delay * (2 ** attempt))
        if self._audit is not None:
            self._audit.record(server, tool, False, error=str(last_err))
        raise ToolUnavailable(f"{server}.{tool} failed after {self._retries} attempts: {last_err}")


class MCPBackend:
    """Call tools over MCP (FastMCP servers, optionally behind the TF MCP Gateway).

    `invoke` matches InProcessBackend's signature so it drops into ToolGateway.
    The live tool-name mapping is verified against the gateway per the runbook.
    """

    def __init__(self, base_url: str, api_key: str | None = None):
        self._base_url = base_url
        # Bearer token for an authenticated gateway (e.g. TF). None/"" → no auth
        # header (the local aggregator needs none).
        self._api_key = api_key or None

    def _tool_name(self, server: str, tool: str) -> str:
        return f"{server}_{tool}"

    async def _acall(self, server: str, tool: str, kwargs: dict):
        from fastmcp import Client

        async with Client(self._base_url, auth=self._api_key) as client:
            result = await client.call_tool(self._tool_name(server, tool), kwargs)
            return getattr(result, "data", result)

    def invoke(self, server: str, tool: str, kwargs: dict):
        try:
            return asyncio.run(self._acall(server, tool, kwargs))
        except ToolFailure:
            raise  # already a transient failure the gateway understands
        except Exception as err:
            # Network/client errors must look transient so ToolGateway retries
            # and degrades to ToolUnavailable (→ queued) instead of crashing.
            raise ToolFailure(f"{self._tool_name(server, tool)} MCP call failed: {err}") from err
