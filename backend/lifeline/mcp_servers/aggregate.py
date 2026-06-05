"""Aggregate the five mock MCP servers into one FastMCP app for deployment.

Each server's tools are mounted under its name so the live tool names match
MCPBackend._tool_name ("chart_get_patient_chart", ...). Run as one HTTP service;
the TF MCP Gateway registers a virtual MCP pointing here.
"""
from fastmcp import FastMCP

from lifeline.mcp_servers import benefits, chart, formulary, insurer, pharmacy

mcp = FastMCP("lifeline-tools")
for module in (chart, formulary, insurer, benefits, pharmacy):
    mcp.mount(module.mcp, namespace=module.SERVER)


if __name__ == "__main__":
    import os

    mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
