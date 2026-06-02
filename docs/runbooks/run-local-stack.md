# Run the Lifeline Local Stack

## Backend (fully local, no TrueFoundry)

```bash
cd backend
# 1. (optional) start the mock MCP servers as processes
.venv/bin/python -m lifeline.scripts.run_servers          # ports 8001-8005

# 2. start the guardrail server (Plan 1)
.venv/bin/python -m lifeline.guardrail.server             # port 8010

# 3. start the bridge API (interactive SSE + batch + chaos + audit)
.venv/bin/uvicorn lifeline.bridge.app:app --port 8000
```

Smoke the bridge:

```bash
# seed + run a small batch
curl -s -X POST localhost:8000/batch/seed \
  -H 'content-type: application/json' \
  -d '{"items":[{"item_id":"item_0001","patient_id":"p_002","request_type":"refill","med_id":"m_ibuprofen","status":"pending"}]}'
curl -s -X POST localhost:8000/batch/run -d '{}'
curl -s localhost:8000/batch/status
# stream an interactive run (SSE)
curl -N -X POST localhost:8000/interactive \
  -H 'content-type: application/json' \
  -d '{"patient_id":"p_001","request_type":"refill","med_id":"m_ibuprofen"}'
# inject + clear chaos
curl -s -X POST localhost:8000/chaos/scenario/tool_outage
curl -s localhost:8000/chaos/state
curl -s -X POST localhost:8000/chaos/clear -d '{}'
```

## Wiring tools through the TF MCP Gateway (demo)

By default the bridge uses the **in-process** tool backend. To route tool calls
through the live TF MCP Gateway instead:

1. Start the MCP servers (step 1 above) and register them behind the virtual MCP
   `lifeline-tools` in the TF console (see `tf-console-setup.md`); **disable
   `cancel_auth`** at the gateway.
2. Swap the bridge's tool backend to `MCPBackend(<gateway-url>)` (see
   `lifeline/agent/tools.py`) and confirm the gateway tool-name mapping matches
   `MCPBackend._tool_name` (`<server>_<tool>`); adjust if the gateway namespaces
   differently.
3. The "disable destructive tool live" demo beat: toggle `cancel_auth` off at the
   gateway — no code change; the agent simply cannot call it.

## Dashboard (Next.js)

```bash
cd frontend
pnpm install
pnpm approve-builds   # one-time: approve sharp / unrs-resolver / msw native builds
pnpm dev              # http://localhost:3000  (expects bridge on :8000)
```

`NEXT_PUBLIC_API_BASE` (in `frontend/.env.local`, default `http://localhost:8000`)
points the dashboard at the bridge.

Demo flow:
1. **Interactive Run** panel → Run (`p_001` / `m_warfarin` / `refill`) → watch nodes stream node-by-node.
2. **Chaos Controls** → click `tool_outage` → re-run interactive → it degrades/queues; **Audit Trail** shows the failed tool call.
3. **Batch Monitor** → Seed 200 → Run with `limit=120` → stop → Run again → resumes the remaining 80 without reprocessing.
4. **Cost / Routing** shows per-model counts (populated once the live LLM is wired via `USE_TF`).
5. **Clear** chaos to reset.

Panels poll the bridge via SWR (deduped, revalidate-on-focus); interactive uses
`fetch` + `ReadableStream` to consume the POST SSE stream.
