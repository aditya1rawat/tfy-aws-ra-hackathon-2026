# TrueFoundry Console Setup (Lifeline) — Phase B1 live wiring

Console configuration to make the deployed stack run live. The three services are
deployed per `tf-deploy.md` (`lifeline-bridge`, `lifeline-mcp`, `lifeline-guardrail`);
this file wires the **AI Gateway**, **MCP Gateway**, and **Guardrails** around them.
Values map to the bridge service's env (and `backend/.env` for local runs).

> Prerequisite: services deployed and healthy (`tf-deploy.md` §3–§5). Have the
> recorded URLs ready: `BRIDGE_URL`, `GUARDRAIL_URL`, MCP service URL.

## 1. AI Gateway — virtual model with fallback + budget

1. Create a provider account for AWS Bedrock (hackathon-provided credentials).
2. Create a **virtual model** (e.g. `lifeline-router`) with:
   - **Primary** → set on the bridge as `TF_PRIMARY_MODEL`.
   - **Fallback** → `TF_FALLBACK_MODEL` (a different provider/model so the fallback beat is visible).
   - Priority/weight routing + a **budget cap** (the gateway-owned resilience layer).
3. Copy the gateway base URL `https://<tenant>.truefoundry.cloud/api/llm/api/inference/openai`
   → `TF_GATEWAY_BASE_URL`. Create an API key → `TF_API_KEY`. Bridge has `USE_TF=true`.

Two independent fallback layers, demoed separately: the gateway's virtual-model fallback
**and** the app-owned `ResilientLLM(ChaosLLM → fallback)`. The `Kill LLM` chaos lever on
`/xray` forces the app layer; a primary-model outage at the gateway exercises the other.

## 2. Custom guardrail — drug-interaction adapter (now a deployed service)

The guardrail is the **`lifeline-guardrail`** service (`GUARDRAIL_URL`), which exposes
both `/check` (called by the bridge's `interaction` node in TF mode) and
`/guardrails/interaction` (called by the AI Gateway).

1. Register a **custom guardrail** of type *input* pointing at
   `${GUARDRAIL_URL}/guardrails/interaction`.
2. Contract (implemented): gateway POSTs `{requestBody, config, context}`; the service
   returns HTTP 200 with `{"verdict": <bool>, "message": "..."}`. `verdict:false` blocks.
   The agent embeds `{"existing_meds": [...], "proposed_med": "..."}` as the last user message.
3. Enable TF's **built-in PHI-redact** guardrail on LLM input (complements the app-owned
   `redact` node). Optional: an output-validation guardrail.

Note the two guardrail layers both surface in the demo: the app's deterministic
`interaction` node block (authoritative, over HTTP to `lifeline-guardrail`) and the
gateway's input-guardrail (defense-in-depth on the LLM call).

Verify the service directly:
```bash
curl -s ${GUARDRAIL_URL}/health
curl -s -X POST ${GUARDRAIL_URL}/check -H 'content-type: application/json' \
  -d '{"existing_meds":["m_warfarin"],"proposed_med":"m_aspirin"}'   # → "decision":"block"
```

## 3. MCP Gateway — scoped virtual MCP

`lifeline-mcp` exposes all five servers' tools from one endpoint, namespaced as
`{server}_{tool}` (e.g. `chart_get_patient_chart`, `pharmacy_approve_refill`,
`insurer_cancel_auth`).

1. Register a **virtual MCP** `lifeline-tools` pointing at the `lifeline-mcp` service URL.
2. **Expose:** all read tools + `insurer_submit_prior_auth`, `benefits_submit_application`,
   `pharmacy_approve_refill`.
3. **Disable `insurer_cancel_auth`** (and any delete) at the gateway — the live demo beat
   is toggling it OFF, enforcing a scoped permission with no code change.
4. Set the bridge's `MCP_GATEWAY_URL` to the **virtual-MCP** URL (not the raw mcp service),
   then restart the bridge.

Verify the routed tool path live:
```bash
curl -s -X POST ${BRIDGE_URL}/patient/request -H 'content-type: application/json' \
  -d '{"patient_id":"p_002","med_id":"m_ibuprofen"}'
curl -s ${BRIDGE_URL}/patient/p_002/requests     # approved; model_used is a real Bedrock id
```

## 4. Observability — link beats to traces

Every gateway LLM call, guardrail decision, and MCP tool call is traced in TF Monitoring.
For the demo, record the trace URL for each of the five beats (see `demo-walkthrough.md`):

| Beat | Axis | Where the trace lives |
|---|---|---|
| Model fallback (Kill LLM / primary outage) | AI Gateway | AI Monitoring → request route shows fallback model |
| Tool degradation + requeue | Resilience + MCP | MCP Gateway → failed tool call, then recovered |
| Guardrail block (aspirin on warfarin) | Guardrails | Guardrail decision + `lifeline-guardrail` logs |
| Durable checkpoint resume (restart bridge mid-run) | Resilience | bridge logs + Neon checkpoint rows |
| `insurer_cancel_auth` rejected at gateway | MCP (scoped perms) | MCP Gateway → blocked tool |

`/system/state` on the bridge is the at-a-glance health: `primary_model`, `active_model`,
`llm_killed`, active chaos, `hydradb` (connected), and degraded flag.
