# DigitalOcean App Platform Deploy — Phase B1 services

TF has no attached cluster, so the three backend services run on **DigitalOcean App
Platform** (free managed HTTPS, which the TF Gateway/MCP callbacks need). TF still
provides the judged **features** (AI Gateway, MCP Gateway, Guardrails) — see
`tf-console-setup.md`. App specs: `backend/deploy/digitalocean/*.yaml`.

> One-time: authorize DigitalOcean's GitHub app for `aditya1rawat/tfy-aws-ra-hackathon-2026`
> (DO console → Apps → Create App → GitHub → install/authorize). App Platform builds
> from the repo + the committed Dockerfiles.

## Order

guardrail → mcp → bridge → (TF console wiring) → set bridge `MCP_GATEWAY_URL` → redeploy.

## 1. lifeline-guardrail (no secrets)

```bash
doctl apps create --spec backend/deploy/digitalocean/guardrail.yaml
doctl apps list   # grab the app id + Default Ingress (the public https URL)
```
Verify once live:
```bash
curl -s <GUARDRAIL_URL>/health        # {"status":"ok"}
curl -s -X POST <GUARDRAIL_URL>/check -H 'content-type: application/json' \
  -d '{"existing_meds":["m_warfarin"],"proposed_med":"m_aspirin"}'   # "decision":"block"
```
Record `GUARDRAIL_URL`.

## 2. lifeline-mcp (no secrets)

```bash
doctl apps create --spec backend/deploy/digitalocean/mcp.yaml
doctl apps list   # grab the public https URL = the MCP endpoint
```
(No `/health` route — App Platform does a TCP readiness check.) Record the MCP URL
for the TF virtual-MCP registration.

## 3. lifeline-bridge (has secrets)

1. Edit `backend/deploy/digitalocean/bridge.yaml`: set `GUARDRAIL_URL`, `TF_PRIMARY_MODEL`,
   `TF_FALLBACK_MODEL`. Leave `MCP_GATEWAY_URL=""` for now.
2. Create, then set secrets in the console (Apps → lifeline-bridge → Settings →
   Environment): `TF_API_KEY`, `DATABASE_URL` (Neon pooled DSN), `HYDRADB_API_KEY`,
   `HYDRADB_TENANT_ID`.
   ```bash
   doctl apps create --spec backend/deploy/digitalocean/bridge.yaml
   ```
3. Verify:
   ```bash
   curl -s <BRIDGE_URL>/health           # {"status":"ok"}
   curl -s <BRIDGE_URL>/system/state     # real primary_model, hydradb:"connected", degraded:false
   ```
Record `BRIDGE_URL`.

## 4. TF console wiring

Follow `tf-console-setup.md` (AI Gateway virtual model + budget; custom guardrail →
`<GUARDRAIL_URL>/guardrails/interaction` + PHI-redact; virtual MCP → the §2 MCP URL with
`insurer_cancel_auth` disabled). Then set the bridge's `MCP_GATEWAY_URL` to the virtual-MCP
URL and redeploy:
```bash
# after editing MCP_GATEWAY_URL in bridge.yaml (or the console env):
doctl apps update <bridge-app-id> --spec backend/deploy/digitalocean/bridge.yaml
```

## 5. Frontend (Vercel)

`NEXT_PUBLIC_API_BASE=<BRIDGE_URL>`; deploy `frontend/`; map `patient.`/`clinic.`/`dashboard.`
(see `tf-deploy.md` §7).

## Redeploy / restart (durable-resume beat)

```bash
doctl apps create-deployment <bridge-app-id>   # force a fresh deploy mid-run → resumes from Neon checkpoint
```

## Recorded values

| Key | Value |
|---|---|
| GUARDRAIL_URL | |
| MCP URL (raw) | |
| MCP virtual-MCP URL (TF) | |
| BRIDGE_URL | |
| bridge app id | |
