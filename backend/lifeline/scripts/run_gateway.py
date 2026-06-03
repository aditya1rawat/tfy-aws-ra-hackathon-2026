"""Local MCP gateway: one FastMCP server that mounts the five mock servers under
their domain namespace (`chart_get_patient_chart`, `insurer_submit_prior_auth`, …).

This is a faithful in-process stand-in for the TrueFoundry virtual MCP
`lifeline-tools`: it exposes the same namespaced tool names that
`MCPBackend._tool_name` expects, and disables the destructive `cancel_auth`
tool at the gateway (the live demo beat — no agent code change needed).

Run it, then point the bridge at it with MCP_GATEWAY_URL=http://127.0.0.1:8009/mcp.
"""
from fastmcp import FastMCP

from lifeline.mcp_servers import benefits, chart, formulary, insurer, pharmacy

# domain namespace → the Plan 1 FastMCP server object
SERVERS = {
    "chart": chart.mcp,
    "formulary": formulary.mcp,
    "insurer": insurer.mcp,
    "benefits": benefits.mcp,
    "pharmacy": pharmacy.mcp,
}

# Tools disabled at the gateway. Mirrors the TF virtual-MCP config: the agent
# simply cannot call these, with no change to agent code.
DISABLED: set[tuple[str, str]] = {("insurer", "cancel_auth")}


def build_gateway(*, disabled: set[tuple[str, str]] = DISABLED) -> FastMCP:
    """Compose the five servers into one namespaced gateway, minus disabled tools."""
    gateway = FastMCP("lifeline-tools")
    for namespace, server in SERVERS.items():
        gateway.mount(server, namespace=namespace)
    # Mounted tools live-link to the source server, so disable at the source.
    for server_name, tool in disabled:
        try:
            SERVERS[server_name].local_provider.remove_tool(tool)
        except Exception:
            pass  # already absent
    return gateway


def main(host: str = "127.0.0.1", port: int = 8009) -> None:
    build_gateway().run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
