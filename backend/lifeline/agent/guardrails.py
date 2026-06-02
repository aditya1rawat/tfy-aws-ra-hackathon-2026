import re

import httpx

from lifeline.data import load_fixture
from lifeline.guardrail.interactions import build_alias_index, check_interactions

_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DOB = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def redact_phi(text: str) -> str:
    """Mutate-mode guardrail: mask SSN and ISO date-of-birth patterns."""
    text = _SSN.sub("[REDACTED]", text)
    text = _DOB.sub("[REDACTED]", text)
    return text


def validate_output(payload, required_keys: list[str]) -> bool:
    """Validate that a tool/LLM payload is a dict carrying every required key."""
    if not isinstance(payload, dict):
        return False
    return all(key in payload for key in required_keys)


def _verdict(existing_meds: list[str], proposed_med: str) -> dict:
    ruleset = load_fixture("interactions.json")
    alias = build_alias_index(load_fixture("medications.json"))
    result = check_interactions(existing_meds, proposed_med, ruleset, alias)
    reason = "; ".join(v["reason"] for v in result["violations"]) or "no interaction"
    return {
        "decision": "block" if result["blocked"] else "allow",
        "violations": result["violations"],
        "reason": reason,
    }


class InProcessInteractionGuardrail:
    """Call the deterministic interaction engine directly (the authoritative 'teeth')."""

    def check(self, existing_meds: list[str], proposed_med: str) -> dict:
        return _verdict(existing_meds, proposed_med)


class HttpInteractionGuardrail:
    """Call the Plan 1 `/check` guardrail server over HTTP."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    def check(self, existing_meds: list[str], proposed_med: str) -> dict:
        resp = httpx.post(
            f"{self._base_url}/check",
            json={"existing_meds": existing_meds, "proposed_med": proposed_med},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()
