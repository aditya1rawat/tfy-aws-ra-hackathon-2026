#!/usr/bin/env bash
# Lifeline demo macros — one shortcut per scene moment.
# Usage:  scripts/demo.sh <command>
#   BURL overrides target (default = prod bridge).  Local: BURL=http://localhost:8000 scripts/demo.sh reset
#
# Commands (grouped by the 3-min video script, demo-video-script-3min.md):
#   state              GET  /system/state                       — health: primary/active model, chaos, hydradb
#   reset              POST /demo/reset                          — CLEAN SLATE (between every chaos beat)
#   clear-chaos        POST /chaos/clear                         — drop chaos only (keep runs)
#   seed-hero          POST /demo/seed_hero                      — write p_001 prior aspirin-escalation memory
#
#   --- Scene 4: telemetry/trace (record FIRST; needs a COMPLETING gateway call) ---
#   clean-refill       POST /patient/request p_001 lisinopril    — 2 real gateway calls → rich telemetry + trace
#
#   --- Scene 1: hero block ---
#   hero               POST /patient/request p_001 aspirin       — interaction guardrail → escalate
#   approve <req_id>   POST /clinic/action approve_alternative   — pharmacist approves acetaminophen alt
#
#   --- Scene 2: dose-hold ---
#   dose-arm           POST /chaos/llm {dose_hallucinate:true}   — arm only (then click /xray Run dose-hold)
#   dose-run           arm + POST /patient/request lisinopril    — headless dose-block (one shot)
#
#   --- Scene 3: kill interaction ---
#   kill-interaction   POST /chaos/set interactions fail         — interaction MCP tool down → degrade
#
#   --- Scene 6 montage ---
#   failover           POST /chaos/llm {gateway_failover:true}   — gateway reroutes sonnet→haiku
#   batch              seed 50 + run async                       — background load (restart-survival shot)
set -euo pipefail

BURL="${BURL:-https://lifeline-bridge-oi9cd.ondigitalocean.app}"
cmd="${1:-help}"; shift || true

_pp() { if command -v jq >/dev/null 2>&1; then jq .; else cat; fi; }
_post() { echo "POST $BURL$1  ${2:+$2}" >&2; curl -fsS -X POST "$BURL$1" \
            ${2:+-H 'content-type: application/json' -d "$2"} | _pp; }
_get()  { echo "GET  $BURL$1" >&2; curl -fsS "$BURL$1" | _pp; }

case "$cmd" in
  state)            _get  /system/state ;;
  reset)            _post /demo/reset ;;
  clear-chaos)      _post /chaos/clear '{}' ;;
  seed-hero)        _post /demo/seed_hero ;;

  clean-refill)     _post /patient/request '{"patient_id":"p_001","med_id":"m_lisinopril","request_type":"refill"}' ;;
  hero)             _post /patient/request '{"patient_id":"p_001","med_id":"m_aspirin","request_type":"refill"}' ;;
  approve)
    [ "${1:-}" ] || { echo "usage: demo.sh approve <request_id>" >&2; exit 2; }
    _post /clinic/action "{\"request_id\":\"$1\",\"action\":\"approve_alternative\",\"note\":\"Acetaminophen alternative approved\"}" ;;

  dose-arm)         _post /chaos/llm '{"dose_hallucinate":true}' ;;
  dose-run)
    _post /chaos/llm '{"dose_hallucinate":true}' >/dev/null
    _post /patient/request '{"patient_id":"p_001","med_id":"m_lisinopril","request_type":"refill"}' ;;

  kill-interaction) _post /chaos/set '{"server":"interactions","tool":"check_interaction","mode":"fail"}' ;;

  failover)         _post /chaos/llm '{"gateway_failover":true}' ;;
  batch)
    _post /batch/seed_n '{"count":50}' >/dev/null
    _post /batch/run_async '{}' ;;

  help|*)
    sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//' ;;
esac
