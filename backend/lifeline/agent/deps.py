from dataclasses import dataclass, field

from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import LLMClient
from lifeline.agent.memory import NullMemoryStore
from lifeline.agent.tools import InProcessBackend, ToolGateway


@dataclass
class Deps:
    llm: LLMClient
    tools: ToolGateway
    guardrail: object  # InProcessInteractionGuardrail | HttpInteractionGuardrail
    audit: object | None = None  # AuditLog — when set, nodes log LLM + guardrail events
    memory: object = field(default_factory=NullMemoryStore)  # MemoryStore — recall/write history
    rlog: object = None  # ResilienceLog — when set, recall node records memory degrades


def decide_action(request_type: str, coverage: dict) -> str:
    """Map request type + formulary coverage to one of refill | prior_auth | benefit."""
    if request_type == "benefit" or not coverage.get("covered", False):
        return "benefit"
    if request_type == "prior_auth" or coverage.get("needs_prior_auth", False):
        return "prior_auth"
    return "refill"


def local_deps(llm: LLMClient) -> Deps:
    """Build a fully in-process Deps stack (used by tests and local runs)."""
    return Deps(
        llm=llm,
        tools=ToolGateway(InProcessBackend()),
        guardrail=InProcessInteractionGuardrail(),
    )
