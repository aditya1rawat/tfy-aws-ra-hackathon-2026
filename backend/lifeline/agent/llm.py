import re
from typing import Protocol

from pydantic import BaseModel

_PID = re.compile(r"\bp_\d+\b")
_MID = re.compile(r"\bm_[a-z]+\b")
_RTYPE = re.compile(r"\b(prior_auth|benefit|refill)\b")


class Intent(BaseModel):
    patient_id: str
    request_type: str          # "refill" | "prior_auth" | "benefit"
    med_id: str


class LLMUnavailable(Exception):
    """Raised when an LLM client cannot produce a result."""


class LLMRateLimited(LLMUnavailable):
    """Injected 429-style rate limit on an LLM client."""


class LLMClient(Protocol):
    name: str

    def parse_intent(self, text: str, *, history: str = "") -> Intent:
        ...


class FakeLLM:
    """Deterministic in-memory LLM for tests. Optionally fails the first N calls."""

    def __init__(self, intent: Intent, fail_times: int = 0, name: str = "fake"):
        self._intent = intent
        self._fail_times = fail_times
        self.name = name

    def parse_intent(self, text: str, *, history: str = "") -> Intent:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise LLMUnavailable(f"{self.name} injected failure")
        return self._intent


class PatternLLM:
    """Deterministic offline intent parser: regex-extract ids/type from free text.

    Stands in for a real model so the free-text intake path works offline for any
    patient. Raises LLMUnavailable (the uniform failure signal) when it can't.
    """

    def __init__(self, name: str = "pattern"):
        self.name = name

    def parse_intent(self, text: str, *, history: str = "") -> Intent:
        pid = _PID.search(text or "")
        mid = _MID.search(text or "")
        if not pid or not mid:
            raise LLMUnavailable(f"{self.name}: could not parse intent from {text!r}")
        rtype = _RTYPE.search(text or "")
        return Intent(
            patient_id=pid.group(0),
            med_id=mid.group(0),
            request_type=rtype.group(1) if rtype else "refill",
        )


class ResilientLLM:
    """Try each client in order; retry each up to `retries` times before moving on.

    Records per-attempt failures + the recovering client to a ResilienceLog (when
    provided), so the x-ray can show the model-fallback story.
    """

    def __init__(self, clients: list[LLMClient], retries: int = 2,
                 rlog=None, run_id_get=None):
        if not clients:
            raise ValueError("ResilientLLM needs at least one client")
        self._clients = clients
        self._retries = retries
        self.name = "resilient"
        self.last_model: str | None = None
        self._rlog = rlog
        self._run_id_get = run_id_get or (lambda: None)

    def _mode_of(self, err: Exception) -> str:
        if isinstance(err, LLMRateLimited):
            return "ratelimit"
        return "fail"

    def parse_intent(self, text: str, *, history: str = "") -> Intent:
        last_err: Exception | None = None
        degraded_once = False  # any failure before the answering client?
        for client in self._clients:
            for attempt in range(self._retries):
                try:
                    out = client.parse_intent(text, history=history)
                    self.last_model = client.name
                    if degraded_once and self._rlog is not None:
                        self._rlog.record(self._run_id_get(), layer="llm",
                                          target=client.name, attempt=attempt + 1,
                                          mode=None, backoff_ms=0, outcome="recovered",
                                          recovered_by=client.name)
                    return out
                except LLMUnavailable as err:
                    last_err = err
                    degraded_once = True
                    if self._rlog is not None:
                        self._rlog.record(self._run_id_get(), layer="llm",
                                          target=client.name, attempt=attempt + 1,
                                          mode=self._mode_of(err), backoff_ms=0,
                                          outcome="fail")
        if self._rlog is not None:
            self._rlog.record(self._run_id_get(), layer="llm", target="(exhausted)",
                              attempt=0, mode=self._mode_of(last_err) if last_err else "fail",
                              backoff_ms=0, outcome="degraded")
        raise LLMUnavailable(f"all LLM clients exhausted: {last_err}")


_INTENT_PROMPT = (
    "Extract the patient_id, request_type (one of refill, prior_auth, benefit), "
    "and med_id from this care-coordinator request:\n\n{text}"
)


def _build_chat_model(base_url: str, api_key: str, model: str):
    """Seam: build a LangChain chat model bound to the TF gateway. Patched in tests."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model,
                      temperature=0, include_response_headers=True)


class TFGatewayLLM:
    """OpenAI-compatible client pointed at the TrueFoundry AI Gateway.

    Captures the gateway's resolved (served) model so a gateway-internal failover
    — the virtual model rerouting to a fallback target — is observable to the app.
    The gateway reports the served model in the standard ``model_name`` response
    metadata (verified live); ``x-tfy-resolved-model`` is a secondary fallback.
    """

    def __init__(self, base_url: str, api_key: str, model: str):
        self.name = model
        self.last_resolved_model: str | None = None
        chat = _build_chat_model(base_url, api_key, model)
        self._structured = chat.with_structured_output(Intent, include_raw=True)

    def parse_intent(self, text: str, *, history: str = "") -> Intent:
        prompt = _INTENT_PROMPT.format(text=text)
        if history:
            prompt = f"Prior visits for this patient: {history}\n\n{prompt}"
        try:
            result = self._structured.invoke(prompt)
        except Exception as err:  # network/429/provider error → uniform signal for ResilientLLM
            raise LLMUnavailable(f"{self.name}: {err}") from err
        raw = result.get("raw")
        meta = getattr(raw, "response_metadata", {}) or {}
        self.last_resolved_model = (
            meta.get("model_name")
            or (meta.get("headers") or {}).get("x-tfy-resolved-model")
        )
        return result["parsed"]


# --- App-level LLM chaos lever (demo: force the primary model to misbehave) ---
import time as _time

_llm_chaos = {"mode": "none"}  # none | fail | ratelimit | slow
_LLM_SLOW_S = 3.0


def set_llm_mode(mode: str) -> None:
    """Set the LLM chaos mode (none|fail|ratelimit|slow)."""
    _llm_chaos["mode"] = mode


def get_llm_mode() -> str:
    return _llm_chaos["mode"]


def set_llm_killed(killed: bool) -> None:
    """Back-compat: kill == fail mode."""
    _llm_chaos["mode"] = "fail" if killed else "none"


def is_llm_killed() -> bool:
    return _llm_chaos["mode"] == "fail"


class ChaosLLM:
    """Wrap an LLM client; inject the current LLM chaos mode on parse_intent.

    none → passthrough; fail → LLMUnavailable; ratelimit → LLMRateLimited;
    slow → sleep then passthrough. Lets the presenter make the primary model
    fail / rate-limit / lag so ResilientLLM falls back.
    """

    def __init__(self, inner: LLMClient):
        self._inner = inner
        self.name = inner.name

    def parse_intent(self, text: str, *, history: str = "") -> Intent:
        mode = get_llm_mode()
        if mode == "fail":
            raise LLMUnavailable(f"{self.name}: killed by chaos")
        if mode == "ratelimit":
            raise LLMRateLimited(f"{self.name}: rate limited by chaos")
        if mode == "slow":
            _time.sleep(_LLM_SLOW_S)
        return self._inner.parse_intent(text, history=history)


# --- Gateway-failover demo lever (route through the chaos virtual model) ---
_gateway_chaos = {"on": False}


def set_gateway_chaos(on: bool) -> None:
    """Toggle the gateway-failover demo: route through the chaos virtual model."""
    _gateway_chaos["on"] = bool(on)


def is_gateway_chaos() -> bool:
    return _gateway_chaos["on"]


class GatewayRouterLLM:
    """Front the gateway client(s). Picks the chaos virtual model when the
    gateway-chaos flag is set, then inspects ``last_resolved_model``: if the
    gateway rerouted away from the primary target, record a ``gateway-failover``
    beat so the x-ray shows the platform-native failover.

    Two-vm path: ``chaos`` is a second TFGatewayLLM bound to the chaos virtual
    model. Single-vm path: pass ``chaos=None`` and have the flag set a
    per-request override on ``healthy`` instead — the beat logic is unchanged.
    """

    def __init__(self, healthy, chaos=None, *, primary_target: str,
                 rlog=None, run_id_get=None):
        self._healthy = healthy
        self._chaos = chaos
        self._primary_target = primary_target
        self._rlog = rlog
        self._run_id_get = run_id_get or (lambda: None)
        self.name = healthy.name
        self.last_resolved_model: str | None = None

    def parse_intent(self, text: str, *, history: str = "") -> Intent:
        client = self._chaos if (is_gateway_chaos() and self._chaos is not None) else self._healthy
        out = client.parse_intent(text, history=history)
        resolved = getattr(client, "last_resolved_model", None)
        self.last_resolved_model = resolved
        if resolved and resolved != self._primary_target and self._rlog is not None:
            self._rlog.record(self._run_id_get(), layer="llm", target="gateway",
                              attempt=1, mode="gateway-failover", backoff_ms=0,
                              outcome="recovered", recovered_by=resolved)
        return out
