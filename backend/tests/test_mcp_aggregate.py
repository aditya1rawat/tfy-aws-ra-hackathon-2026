import asyncio

from fastmcp import Client

from lifeline.mcp_servers.aggregate import mcp


def test_aggregated_tools_are_namespaced():
    async def go():
        async with Client(mcp) as c:
            return {t.name for t in await c.list_tools()}
    names = asyncio.run(go())
    assert "chart_get_patient_chart" in names
    assert "pharmacy_approve_refill" in names
    assert "insurer_cancel_auth" in names  # present in code; disabled at the gateway


def test_aggregated_tool_executes():
    async def go():
        async with Client(mcp) as c:
            res = await c.call_tool("chart_get_patient_chart", {"patient_id": "p_001"})
            return getattr(res, "data", res)
    out = asyncio.run(go())
    assert out["patient_id"] == "p_001"
