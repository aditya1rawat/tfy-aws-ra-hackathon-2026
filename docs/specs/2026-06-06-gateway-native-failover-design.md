# Gateway-Native Model Failover (Feature E) — Design

**Date:** 2026-06-06
**Feature:** E of the gateway-expansion set (E → A → C → F)
**Theme tie:** Resilient Agents — pushes model-to-model resilience down into the TrueFoundry AI Gateway, adding a platform-native failover beat on top of the existing 9-beat in-code resilience story.

## Goal

Move LLM model→model failover out of application code and into a TrueFoundry **Virtual Model** with a priority-based fallback chain. The application calls a single virtual model name; the gateway reroutes on provider errors. Surface the gateway's failover decision as a new resilience beat in `/xray`, and keep the application's own resilience layers (retry, circuit, degrade-to-deterministic, chaos) intact.

## Architecture — Hybrid Split

Two resilience layers with a clean division of responsibility:

- **Gateway layer (new):** A Virtual Model `lifeline/resilient-chat` owns model→model failover. Chain: `bedrock-sonnet → bedrock-haiku → anthropic-sonnet (worst-case)`. Bedrock variants are preferred (stay on AWS); the Anthropic-direct target is the worst-case cross-provider escape hatch, reached only if Bedrock is fully unavailable. The application never iterates models.
- **App layer (kept):** `ResilientLLM` still wraps the gateway call for retry and the final **degrade-to-offline** path (`PatternLLM`, deterministic regex intent parse) when the *entire* gateway is unreachable. Timeout, circuit-breaker, and the chaos lever are unchanged.

Current code:
```python
ResilientLLM([ChaosLLM(primary_model), fallback_model])   # two concrete gateway models
```
New code:
```python
ResilientLLM([ gateway(virtual_model), PatternLLM(offline) ])  # model fallback now in gateway
```

The two-concrete-model list collapses into the single virtual-model entry. This yields two distinct, separately-demoable failovers:

1. **Gateway-internal failover** (`sonnet → haiku → anthropic`) — proven by the `x-tfy-resolved-model` response header. The new (10th) resilience beat.
2. **App degrade-to-offline** (gateway unreachable → `PatternLLM`) — the existing beat, preserved.

## Gateway Configuration (operator prerequisite, set in TFY UI)

Register the underlying models (Bedrock Sonnet + Haiku, Anthropic Sonnet) as gateway models, then create **two** virtual models.

Healthy virtual model:
```yaml
# lifeline/resilient-chat
routing_config:
  type: priority-based-routing
  load_balance_targets:
    - target: bedrock-main/claude-sonnet-4-6      # primary
      fallback_status_codes: ["429","500","502","503"]
    - target: bedrock-main/claude-haiku-4-5        # same-provider degrade
    - target: anthropic-main/claude-sonnet-4-6     # worst-case cross-provider
```

Chaos virtual model (demo trigger — primary deliberately broken so the gateway always reroutes):
```yaml
# lifeline/resilient-chat-chaos
routing_config:
  type: priority-based-routing
  load_balance_targets:
    - target: bedrock-broken/invalid-deployment    # always 5xx → forces reroute
      fallback_status_codes: ["401","403","404","429","500","502","503"]
    - target: bedrock-main/claude-haiku-4-5         # gateway lands here
    - target: anthropic-main/claude-sonnet-4-6
```

Target ids are placeholders for whatever the gateway integrations are named in the account (e.g. the current config uses the `bedrock-main/anthropic.claude-3-5-sonnet` form). The operator substitutes the real ids.

The application resolves which target actually served a request via the `x-tfy-resolved-model` response header.

## Demo Trigger (deterministic; the gateway performs the real reroute)

A new chaos lever, **"Gateway failover"**, swaps the application's active model string from `resilient-chat` to `resilient-chat-chaos`. The gateway's primary target returns 5xx, the gateway reroutes to the haiku target, and the response carries `x-tfy-resolved-model: …haiku`. The application reads the header and records the gateway-failover beat.

This is deterministic and presenter-controlled, while the failover itself genuinely happens at the gateway (provable via the header). It is independent of the existing **"Kill LLM"** lever, which triggers the app-layer degrade-to-offline path.

## Components / Files

- `backend/lifeline/config.py` — add `virtual_model` and `chaos_virtual_model` settings (env `TF_VIRTUAL_MODEL`, `TF_CHAOS_VIRTUAL_MODEL`).
- `backend/lifeline/agent/llm.py` —
  - `TFGatewayLLM` built with `include_response_headers=True` and `.with_structured_output(Intent, include_raw=True)`; capture `x-tfy-resolved-model` into `last_resolved_model`.
  - A small selector so the gateway client targets the healthy-vs-chaos virtual model based on a flag (`set_gateway_chaos(bool)` / `is_gateway_chaos()`).
- `backend/lifeline/bridge/app.py` —
  - `_build_llm` points at the virtual model; the second client becomes `PatternLLM` (offline degrade).
  - Extend the chaos lever (`/chaos/llm` or a sibling) to accept a `gateway_failover` mode.
  - Record the gateway-failover beat; surface the resolved model in `/system/state`.
- Resilience log — new beat `layer="llm", mode="gateway-failover", recovered_by=<resolved model>`. Reuses the existing `ResilienceEvent` shape; `/xray` renders it with no schema change.
- Frontend — `/xray` chaos controls gain a "Gateway failover" button; the beat appears in the resilience list automatically. Patient screen surfacing is optional (out of scope for E).

## Data Flow

1. Patient/clinic request → agent `intake` node → `ResilientLLM.parse_intent`.
2. First client = gateway client → `TFGatewayLLM` invokes the active virtual model on the TF gateway.
3. Gateway routes per `routing_config`; on primary 5xx it reroutes within the chain.
4. Response returns parsed `Intent` + `x-tfy-resolved-model` header.
5. Client stores `last_resolved_model`. If resolved != primary target, a `gateway-failover` beat is recorded to the resilience log.
6. If the gateway call raises (whole gateway down), `ResilientLLM` falls to `PatternLLM` (offline degrade beat).
7. `/xray` resilience view renders both beat types.

## Error Handling

- **Header missing** (gateway or `langchain-openai` does not surface it): no beat recorded, `Intent` still parsed — no functional break.
- **Gateway fully down:** `LLMUnavailable` → `PatternLLM` offline degrade (existing).
- **Chaos virtual model, all targets fail:** `LLMUnavailable` → offline degrade. Safe.

## Testing

- Unit (`backend/.venv/bin/pytest`): patch the `_build_chat_model` seam to return a fake structured-output object yielding `{parsed: Intent, raw: AIMessage-with-response_metadata.headers}`; assert the header is captured and a `gateway-failover` beat is recorded when resolved != primary. Assert the selector swaps healthy↔chaos. Assert the offline degrade path is unchanged.
- No live provider required for tests (seam patched).
- Frontend (`vitest`): the new beat renders in the resilience list; the "Gateway failover" lever calls the right endpoint.

## Implementation Risk (verify first)

Capturing `x-tfy-resolved-model` depends on `langchain-openai` surfacing the custom response header via `include_raw=True`. The plan's first task is a tiny probe to confirm. Fallbacks if it does not surface: (a) a thin `httpx` raw call to read the header, or (b) defer the visible readout to feature F (gateway traces). Feature E still functions without the header — it only loses the inline beat.

## Out of Scope (YAGNI)

- Patient-screen surfacing of the gateway-failover beat (xray-only for E).
- Weight/latency-based routing experiments (priority-based only).
- Cost/token analytics from the gateway (belongs to feature F).
- Removing the app-layer resilience (explicitly kept per the hybrid split).
