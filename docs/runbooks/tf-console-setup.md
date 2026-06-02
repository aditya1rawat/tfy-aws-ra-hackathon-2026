# TrueFoundry Console Setup (Lifeline)

Configuration steps to wire the Plan 2 agent core to the live TrueFoundry stack.
Code is already written; this is console configuration. Values map to `backend/.env`.

## 1. AI Gateway — virtual model with fallback + budget

1. Create a provider account for AWS Bedrock (the hackathon-provided credentials).
2. Create a **virtual model** (e.g. `lifeline-router`) with:
   - **Primary:** `bedrock-main/anthropic.claude-3-5-sonnet` → set `TF_PRIMARY_MODEL`.
   - **Fallback:** `bedrock-main/meta.llama3-1-8b` → set `TF_FALLBACK_MODEL`.
   - Priority/weight routing + a **budget cap** (gateway-owned resilience layer).
3. Copy the gateway base URL `https://<tenant>.truefoundry.cloud/api/llm/api/inference/openai`
   → `TF_GATEWAY_BASE_URL`. Create an API key → `TF_API_KEY`. Set `USE_TF=true`.

The app-owned `ResilientLLM` fallback (Task 3) sits on top of this gateway fallback —
two independent layers, demoed separately.

## 2. Custom guardrail — drug-interaction adapter

1. Deploy / expose `lifeline.guardrail.tf_adapter:app` (Task 9) at a reachable URL.
2. In the console, register a **custom guardrail** of type *input* pointing at
   `https://<host>/guardrails/interaction`.
3. Contract (already implemented): gateway POSTs `{requestBody, config, context}`;
   server returns HTTP 200 with `{"verdict": <bool>, "message": "..."}`.
   `verdict:false` blocks. The agent embeds
   `{"existing_meds": [...], "proposed_med": "..."}` as the last user message.
4. Also enable TF's **built-in PHI-redact** guardrail on LLM input (complements the
   app-owned `redact` node) and an **output-validation** guardrail if desired.

## 3. MCP Gateway — scoped virtual MCP (wired in Plan 3)

Plan 3 runs the Plan 1 FastMCP servers as processes and registers them behind a
virtual MCP `lifeline-tools`:
- Expose: all READ tools + `submit_prior_auth`, `submit_application`, `approve_refill`.
- **Disable `cancel_auth`** (and any delete) at the gateway — the live demo beat is
  toggling it OFF without a code change.
- Point the agent's Plan 3 MCP backend at the gateway URL (`MCP_GATEWAY_URL`).

## 4. Observability

Every gateway LLM call and guardrail decision is traced in TF AI Monitoring; link each
demo failure→recovery to its request trace.
