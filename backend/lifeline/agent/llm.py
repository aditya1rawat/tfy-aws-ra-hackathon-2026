from typing import Protocol

from pydantic import BaseModel


class Intent(BaseModel):
    patient_id: str
    request_type: str          # "refill" | "prior_auth" | "benefit"
    med_id: str


class LLMUnavailable(Exception):
    """Raised when an LLM client cannot produce a result."""


class LLMClient(Protocol):
    name: str

    def parse_intent(self, text: str) -> Intent:
        ...


class FakeLLM:
    """Deterministic in-memory LLM for tests. Optionally fails the first N calls."""

    def __init__(self, intent: Intent, fail_times: int = 0, name: str = "fake"):
        self._intent = intent
        self._fail_times = fail_times
        self.name = name

    def parse_intent(self, text: str) -> Intent:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise LLMUnavailable(f"{self.name} injected failure")
        return self._intent


class ResilientLLM:
    """Try each client in order; retry each up to `retries` times before moving on.

    Implements the app-owned model-fallback layer that complements the TF
    gateway's own virtual-model fallback.
    """

    def __init__(self, clients: list[LLMClient], retries: int = 2):
        if not clients:
            raise ValueError("ResilientLLM needs at least one client")
        self._clients = clients
        self._retries = retries
        self.name = "resilient"
        self.last_model: str | None = None

    def parse_intent(self, text: str) -> Intent:
        last_err: Exception | None = None
        for client in self._clients:
            for _ in range(self._retries):
                try:
                    out = client.parse_intent(text)
                    self.last_model = client.name
                    return out
                except LLMUnavailable as err:
                    last_err = err
        raise LLMUnavailable(f"all LLM clients exhausted: {last_err}")


_INTENT_PROMPT = (
    "Extract the patient_id, request_type (one of refill, prior_auth, benefit), "
    "and med_id from this care-coordinator request:\n\n{text}"
)


def _build_chat_model(base_url: str, api_key: str, model: str):
    """Seam: build a LangChain chat model bound to the TF gateway. Patched in tests."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model, temperature=0)


class TFGatewayLLM:
    """OpenAI-compatible client pointed at the TrueFoundry AI Gateway."""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.name = model
        chat = _build_chat_model(base_url, api_key, model)
        self._structured = chat.with_structured_output(Intent)

    def parse_intent(self, text: str) -> Intent:
        try:
            return self._structured.invoke(_INTENT_PROMPT.format(text=text))
        except Exception as err:  # network/429/provider error → uniform signal for ResilientLLM
            raise LLMUnavailable(f"{self.name}: {err}") from err
