# Lifeline — Demo Walkthrough (Phase A)

The live narration script for the judges. Three product surfaces, one agent, two on-demand resilience levers. Everything below runs **offline** (`USE_TF=false`) — deterministic and reproducible. The live-TF variant is noted at the end.

## Surfaces

| Surface | Local URL | Subdomain (prod) | Who |
|---|---|---|---|
| Patient portal | http://localhost:3000/patient | `patient.<domain>` | John Doe (patient) |
| Clinic console | http://localhost:3000/clinic | `clinic.<domain>` | R. Okafor, PharmD |
| X-ray / ops | http://localhost:3000/xray | `dashboard.<domain>` | you (engineer) |

Persona switcher (top bar) flips between them on a non-product host; it is hidden on the product subdomains so a judge on `patient.<domain>` sees only the patient app.

## Start the stack (offline)

```bash
# backend (deterministic, fallback demoable, no live calls)
cd backend && USE_TF=false .venv/bin/uvicorn lifeline.bridge.app:app --port 8000 --host 127.0.0.1

# frontend
cd frontend && pnpm dev   # http://localhost:3000
```

Reset between runs: restart the backend (the RequestStore is in-memory, so this clears the queue). Clear chaos with the X-ray **Clear chaos** button.

## The two resilience levers

1. **Model fallback** — X-ray **Kill LLM** sets an app chaos flag. The next request's free-text intake call fails on the primary (`sonnet-sim`) and `ResilientLLM` falls back to `haiku-sim`. Surfaces as the amber "taking longer" strip (patient) and "fallback model active" strip (clinic); proven in the X-ray log (`FALL primary killed → fallback`).
2. **Graceful degrade / recover** — X-ray **Kill chart tool** makes the `load_context` node degrade to `queued`. The request shows "taking longer"; recover it from the Batch panel **Requeue** button.

## Hero flow (the main arc — ~3 min)

1. **X-ray** → click **Kill LLM**. Point out the chaos lever: "I've just taken down the primary model."
2. **Patient portal** → in *Request a medication*, pick **Aspirin 325mg**, Submit.
   - John is on warfarin. Watch the request card: amber **"taking a little longer than usual"** strip (the fallback firing), then it resolves to **escalated** with the safety note + the pharmacist's **Acetaminophen** alternative.
3. **Clinic console** → John's request sits in the queue as **Escalated**. Select it.
   - "What the agent did": verified patient & coverage → checked against current meds → **🛑 Safety check blocked** (aspirin + warfarin bleeding risk) → escalated. Plus the red **Do not auto-approve** flag and the suggested alternative.
   - Top strip: **"AI provider degraded → fallback model active (haiku-sim)"**.
   - Click **Approve alternative & notify patient**.
4. **Patient portal** → next poll flips the request to **Approved**: "Approved a safe alternative: Acetaminophen 500 mg."
5. **X-ray** → the **Event stream** shows the full machine trace for the run: `GATE route model=haiku-sim`, the `BLOCK` line, `FALL primary killed → fallback`. The proof panels show active_model = haiku-sim, MCP tools scoped, last run escalated.
6. Click **Clear chaos** — strips return to normal.

### Which judging axis each beat proves
- **AI Gateway fallback** → step 2's degraded strip + step 5's `FALL` log line.
- **Guardrails** → step 3's 🛑 block + flag.
- **MCP safe tool access** → X-ray proof panel (9 tools, Bearer, cancel_auth off, audited).
- **Resilience / graceful degrade** → the tool-failure lever (below) + 0-lost batch backdrop.
- **Usefulness** → the patient never sees an error; gets a safe alternative.
- **Demo clarity** → product surface + x-ray side by side: what failed, how it recovered, why.

## Graceful-degrade beat (optional, ~1 min)

1. **X-ray** → **Kill chart tool**.
2. **Patient portal** → submit any request (e.g. Atorvastatin). It shows the **"taking longer"** strip and stays in-review (the `load_context` node degraded to queue).
3. **X-ray** → Batch panel → **Requeue**; clear the tool chaos. The request recovers and completes.

## Batch backdrop (the "at scale" line)

In the X-ray Batch panel, **Seed 200** + **Run** to show the overnight queue processing. Narrate: the same agent runs hundreds of refills overnight; a mid-run provider outage requeues in-flight items with 0 lost (already covered by the batch requeue tests).

## Live-TF variant

Flip `USE_TF=true` and the same flows run against the real TrueFoundry gateway (Sonnet → Haiku), the live MCP gateway (9 tools), and the registered custom guardrail. That path needs the two tunnels up (MCP ngrok + guardrail localtunnel) and the console URLs re-pasted if they rotated — see `docs/runbooks/tf-console-setup.md` and the `tf-live-config` notes. The offline path above needs none of that and is the safe demo default.
