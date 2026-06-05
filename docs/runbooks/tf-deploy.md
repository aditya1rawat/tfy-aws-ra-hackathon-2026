# TrueFoundry Deploy Runbook — Phase B1 (live stack)

Deploy the three backend services on TrueFoundry, the frontend on Vercel, and the
managed DBs (NeonDB + HydraDB). Code is built and committed; this is provisioning +
configuration. Record every URL/secret here (without passwords) as you go.

> Order matters: Neon → guardrail → mcp → bridge → TF console wiring → Vercel.
> Pin every service to `replicas=1` (SQLite/in-memory fallbacks assume one instance;
> Postgres makes >1 safe later, but keep it simple for the demo).

## 0. Prereqs

- Backend image build context is `backend/` (Dockerfiles in `backend/deploy/`).
- Local three-service smoke already verified (`backend/deploy/compose.smoke.yml`).
- Secrets used (never commit): `TF_API_KEY`, `DATABASE_URL`, `HYDRADB_API_KEY`, `HYDRADB_TENANT_ID`.

## 1. NeonDB (serverless Postgres)

1. Create a Neon project + database.
2. Copy the **pooled** connection string → `DATABASE_URL` (bridge secret).
3. Create a throwaway branch DSN → `TEST_DATABASE_URL` for the Postgres parity tests
   (`tests/test_pg_job_store.py`, `tests/test_pg_request_store.py`).
4. Record (no password): host = `__________`, db = `__________`.

Verify parity tests against the branch:
```bash
cd backend && TEST_DATABASE_URL='postgresql://…branch…' \
  .venv/bin/python -m pytest tests/test_pg_job_store.py tests/test_pg_request_store.py -q
# expected: 6 passed
```

## 2. HydraDB

1. Provision a HydraDB tenant; get `HYDRADB_API_KEY` + `HYDRADB_TENANT_ID`.
2. Confirm the health base URL (the client defaults to `https://api.hydradb.io`; update
   `backend/lifeline/bridge/hydradb.py:_BASE` if the tenant uses a different host).
3. These are bridge secrets. `/system/state` will report `hydradb: connected` once set.
   (No memory feature yet — provisioning only.)

## 3. Deploy `lifeline-guardrail`

- TF Service from `backend/deploy/Dockerfile.guardrail`, port **8010**, public, health `/health`, `replicas=1`.
- Public URL → record as `GUARDRAIL_URL` = `__________`.
- Verify: `curl -s https://<guardrail>/health` → `{"status":"ok"}`;
  `curl -s -X POST https://<guardrail>/check -H 'content-type: application/json' -d '{"existing_meds":["m_warfarin"],"proposed_med":"m_aspirin"}'` → `"decision":"block"`.

## 4. Deploy `lifeline-mcp`

- TF Service from `backend/deploy/Dockerfile.mcp`, port **8000**, public, `replicas=1`.
- Public URL → the MCP HTTP endpoint = `__________` (used by the TF virtual MCP in §6).

## 5. Deploy `lifeline-bridge`

- TF Service from `backend/deploy/Dockerfile.bridge`, port **8000**, public, health `/health`, `replicas=1`.
- Env / secrets:
  - `USE_TF=true`
  - `TF_GATEWAY_BASE_URL`, `TF_API_KEY` (secret)
  - `TF_PRIMARY_MODEL`, `TF_FALLBACK_MODEL`
  - `MCP_GATEWAY_URL` = the TF **virtual-MCP** URL from §6 (not the raw mcp service)
  - `GUARDRAIL_URL` = the §3 guardrail URL
  - `DATABASE_URL` (secret, Neon §1)
  - `HYDRADB_API_KEY`, `HYDRADB_TENANT_ID` (secrets, §2)
- Public URL → `BRIDGE_URL` = `__________`.
- Verify:
  ```bash
  curl -s https://<bridge>/health
  curl -s https://<bridge>/system/state   # primary_model real, hydradb connected, degraded:false
  ```

## 6. TF console wiring

See `tf-console-setup.md` for the detailed steps (AI Gateway virtual model + budget +
custom guardrail + PHI-redact; MCP Gateway virtual MCP → §4 service with
`insurer_cancel_auth` **disabled**). Set the bridge's `MCP_GATEWAY_URL` to the virtual-MCP URL,
then restart the bridge.

## 7. Frontend on Vercel

1. Vercel project from `frontend/`. Set `NEXT_PUBLIC_API_BASE=https://<bridge>`.
2. Local prod-build check: `cd frontend && NEXT_PUBLIC_API_BASE=https://<bridge> pnpm build`.
3. Deploy. Add domains `patient.`/`clinic.`/`dashboard.` pointing at the project
   (host-rewrite middleware routes them; persona switcher is the apex fallback).
4. Record: apex = `__________`, patient/clinic/dashboard = `__________`.
5. Verify: load the patient URL, submit a request, confirm it appears in clinic + xray
   (all served by the live bridge).

## Recorded values

| Key | Value |
|---|---|
| BRIDGE_URL | |
| GUARDRAIL_URL | |
| MCP service URL | |
| MCP virtual-MCP URL | |
| Neon host/db | |
| Frontend apex | |
