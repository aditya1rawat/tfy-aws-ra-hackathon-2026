import asyncio

from fastmcp import Client

from lifeline.scripts.run_gateway import build_gateway


def _tool_names() -> list[str]:
    gateway = build_gateway()

    async def go():
        async with Client(gateway) as client:
            return sorted(t.name for t in await client.list_tools())

    return asyncio.run(go())


def test_gateway_namespaces_every_server():
    names = _tool_names()
    # Each domain tool is exposed as `<server>_<tool>` — the form MCPBackend builds.
    assert "chart_get_patient_chart" in names
    assert "formulary_check_coverage" in names
    assert "insurer_submit_prior_auth" in names
    assert "benefits_search_programs" in names
    assert "pharmacy_approve_refill" in names


def test_cancel_auth_disabled_at_gateway():
    # The destructive tool is excluded — the agent cannot call it through the gateway.
    assert "insurer_cancel_auth" not in _tool_names()


def test_gateway_tool_name_matches_backend_mapping():
    from lifeline.agent.tools import MCPBackend

    backend = MCPBackend("http://x")
    assert backend._tool_name("insurer", "submit_prior_auth") in _tool_names()
