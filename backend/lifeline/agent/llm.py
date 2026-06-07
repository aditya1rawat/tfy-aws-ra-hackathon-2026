import re
import time
from typing import Protocol

from pydantic import BaseModel

from lifeline.agent.pricing import price
from lifeline.agent.trace import build_trace_url


def _usage_from(raw):
    """(prompt, completion) tokens from a raw AIMessage, trying usage_metadata
    (newer) then response_metadata['token_usage']. Returns (None, None) on miss."""
    um = getattr(raw, "usage_metadata", None) or {}
    if um.get("input_tokens") is not None:
        return um.get("input_tokens"), um.get("output_tokens")
    tu = (getattr(raw, "response_metadata", {}) or {}).get("token_usage") or {}
    return tu.get("prompt_tokens"), tu.get("completion_tokens")


_REQUEST_ID_HEADERS = ("x-tfy-request-id", "x-request-id", "x-trace-id", "traceparent")


def _request_id_from(raw):
    meta = getattr(raw, "response_metadata", {}) or {}
    headers = meta.get("headers") or {}
    for key in _REQUEST_ID_HEADERS:  # prefer the gateway's own request/trace id
        if headers.get(key):
            return headers[key]
    return meta.get("request_id") or meta.get("id") or getattr(raw, "id", None)


def _record_call(tlog, run_id_get, trace_base_url, *, raw, model, latency_ms):
    """Best-effort: record one telemetry row. Never raises."""
    if tlog is None:
        return
    try:
        prompt, completion = _usage_from(raw)
        rid = _request_id_from(raw)
        tlog.record(run_id_get(), model=model, prompt_tokens=prompt,
                    completion_tokens=completion, latency_ms=latency_ms,
                    cost=price(model, prompt, completion), request_id=rid,
                    trace_url=build_trace_url(trace_base_url, rid))
    except Exception:
        pass


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


class GatewayGuardrailBlocked(Exception):
    """The TF gateway rejected a draft because a guardrail (e.g. dosage) failed.
    Distinct from LLMUnavailable: this is enforcement, not an outage — the draft
    node turns it into a dosage-block beat rather than a degrade."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _failed_guardrail_message(payload: dict) -> str | None:
    """Pull the specific message of the first failed guardrail from a gateway
    400 payload (the `guardrail_checks` object), if present."""
    checks = payload.get("guardrail_checks") or {}
    for hook in ("output_guardrails", "input_guardrails"):
        for entry in checks.get(hook, []) or []:
            if entry.get("result") == "failed":
                msg = (((entry.get("data") or {}).get("guardrailResponse") or {})
                       .get("message"))
                if msg:
                    return msg
    return None


def _guardrail_block_reason(err: Exception) -> str | None:
    """If `err` is a gateway guardrail rejection (HTTP 400 guardrail_checks_failed),
    return the most specific message available; otherwise None. The openai SDK
    flattens `.body` to {message,type,code} and drops guardrail_checks, so reach
    for the raw `.response` JSON first to recover the per-guardrail detail."""
    resp = getattr(err, "response", None)
    if resp is not None:
        try:
            specific = _failed_guardrail_message(resp.json())
            if specific:
                return specific
        except Exception:
            pass
    body = getattr(err, "body", None)
    if isinstance(body, dict):
        specific = _failed_guardrail_message(body)
        if specific:
            return specific
        is_guardrail = (body.get("type") == "guardrail_checks_failed"
                        or body.get("error", {}).get("type") == "guardrail_checks_failed")
        if is_guardrail:
            return body.get("message") or "blocked by gateway guardrail"
    if "guardrail_checks_failed" in str(err):
        return "blocked by gateway guardrail"
    return None


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

    def __init__(self, base_url: str, api_key: str, model: str,
                 *, tlog=None, run_id_get=None, trace_base_url: str = ""):
        self.name = model
        self.last_resolved_model: str | None = None
        self._tlog = tlog
        self._run_id_get = run_id_get or (lambda: None)
        self._trace_base_url = trace_base_url
        chat = _build_chat_model(base_url, api_key, model)
        self._structured = chat.with_structured_output(Intent, include_raw=True)

    def parse_intent(self, text: str, *, history: str = "") -> Intent:
        prompt = _INTENT_PROMPT.format(text=text)
        if history:
            prompt = f"Prior visits for this patient: {history}\n\n{prompt}"
        t0 = time.perf_counter()
        try:
            result = self._structured.invoke(prompt)
        except Exception as err:  # network/429/provider error → uniform signal for ResilientLLM
            raise LLMUnavailable(f"{self.name}: {err}") from err
        latency_ms = int((time.perf_counter() - t0) * 1000)
        raw = result.get("raw")
        meta = getattr(raw, "response_metadata", {}) or {}
        self.last_resolved_model = (
            meta.get("model_name")
            or (meta.get("headers") or {}).get("x-tfy-resolved-model")
        )
        _record_call(self._tlog, self._run_id_get, self._trace_base_url,
                     raw=raw, model=self.last_resolved_model or self.name,
                     latency_ms=latency_ms)
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


# --- Dosage draft: produce the patient-facing reply WITH a dose to be guarded ---

class DraftReply(BaseModel):
    med_id: str          # echoed so the gateway output guardrail can see which med
    message: str
    dose_mg: float
    frequency_per_day: int


# Demo lever: when armed, the drafter emits a deliberately unsafe dose so the
# dosage guardrail visibly blocks it (mirrors the gateway-failover lever).
_dose_chaos = {"on": False}
_UNSAFE_DOSE_MG = 80.0  # over the lisinopril 40 mg ceiling used by the hero demo


def set_dose_chaos(on: bool) -> None:
    _dose_chaos["on"] = bool(on)


def is_dose_chaos() -> bool:
    return _dose_chaos["on"]


_DRAFT_PROMPT = (
    "You are a pharmacy assistant writing a short, friendly refill confirmation for "
    "the patient. Medication: {med}. State the dose clearly. The prescribed dose is "
    "{prescribed} mg once daily. Reply with the message, the dose in mg, the "
    "times-per-day, and set med_id to exactly \"{med_id}\"."
)
class TemplatedDrafter:
    """Offline/fallback drafter. Deterministic: prescribed dose when calm, the
    unsafe dose when chaos is armed. Used by tests and the no-gateway path."""

    name = "templated-drafter"

    def draft(self, med_id: str, prescribed: float | None, *, chaos: bool) -> DraftReply:
        dose = _UNSAFE_DOSE_MG if chaos else (prescribed if prescribed is not None else 0.0)
        med = med_id.removeprefix("m_")
        return DraftReply(
            med_id=med_id,
            message=f"Your {med} refill is ready — take {dose:g} mg once daily.",
            dose_mg=dose, frequency_per_day=1,
        )


class GatewayDrafter:
    """Draft via the TF gateway (structured output). On any provider error raise
    LLMUnavailable so the draft node degrades to a dose-free message."""

    def __init__(self, base_url: str, api_key: str, model: str,
                 *, tlog=None, run_id_get=None, trace_base_url: str = ""):
        self.name = model
        self._tlog = tlog
        self._run_id_get = run_id_get or (lambda: None)
        self._trace_base_url = trace_base_url
        chat = _build_chat_model(base_url, api_key, model)
        self._structured = chat.with_structured_output(DraftReply, include_raw=True)

    def draft(self, med_id: str, prescribed: float | None, *, chaos: bool) -> DraftReply:
        # Chaos: state the unsafe dose AS the prescribed dose. Appending a
        # contradicting override loses to the prescribed line — the model keeps
        # drafting the safe dose, so the guardrail never sees anything unsafe.
        effective = float(_UNSAFE_DOSE_MG) if chaos else prescribed
        prompt = _DRAFT_PROMPT.format(med=med_id.removeprefix("m_"), med_id=med_id,
                                      prescribed=effective if effective is not None else "the usual")
        t0 = time.perf_counter()
        try:
            result = self._structured.invoke(prompt)
        except Exception as err:  # network/429/provider → uniform degrade signal
            reason = _guardrail_block_reason(err)
            if reason is not None:  # gateway enforcement, not an outage
                raise GatewayGuardrailBlocked(reason) from err
            raise LLMUnavailable(f"{self.name} draft: {err}") from err
        latency_ms = int((time.perf_counter() - t0) * 1000)
        raw = result.get("raw")
        model = (getattr(raw, "response_metadata", {}) or {}).get("model_name") or self.name
        _record_call(self._tlog, self._run_id_get, self._trace_base_url,
                     raw=raw, model=model, latency_ms=latency_ms)
        reply = result["parsed"]
        reply.med_id = med_id  # trust the known id, not the model's echo, downstream
        return reply
