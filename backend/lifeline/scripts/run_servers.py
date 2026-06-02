"""Launch the five mock FastMCP servers as subprocesses for local/demo runs.

Each server is a module with an `mcp.run(...)` __main__ block (Plan 1). This
script starts them together and waits; Ctrl-C stops all.
"""
import subprocess
import sys

SERVERS = ["chart", "formulary", "insurer", "benefits", "pharmacy"]


def main() -> None:
    procs = []
    try:
        for name in SERVERS:
            procs.append(subprocess.Popen([sys.executable, "-m", f"lifeline.mcp_servers.{name}"]))
        print(f"started {len(procs)} MCP servers: {', '.join(SERVERS)}")
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("stopping servers")
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()  # force-stop any process that ignored SIGTERM


if __name__ == "__main__":
    main()
