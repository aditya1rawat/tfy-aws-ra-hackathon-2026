from langgraph.graph import END, START, StateGraph

from lifeline.agent import nodes
from lifeline.agent.deps import Deps
from lifeline.agent.state import ItemState, Status


def _route_after_load(state: ItemState) -> str:
    return "finalize" if state["status"] == Status.QUEUED else "interaction"


def _route_after_interaction(state: ItemState) -> str:
    return "finalize" if state["status"] == Status.ESCALATED else "coverage"


def _route_after_coverage(state: ItemState) -> str:
    return "finalize" if state["status"] == Status.QUEUED else "act"


def _route_after_act(state: ItemState) -> str:
    return "finalize" if state["status"] in Status.TERMINAL else "validate"


def _route_after_validate(state: ItemState) -> str:
    # Only the approved refill path drafts a dose-bearing reply to guard.
    if state["status"] == Status.DONE and state.get("action") == "refill":
        return "draft"
    return "finalize"


def _bind(node_fn, deps: Deps):
    """Wrap a node as a clean single-arg callable so LangGraph injects only state."""
    def _node(state: ItemState) -> dict:
        return node_fn(state, deps=deps)
    return _node


def build_graph(deps: Deps, *, checkpointer, interrupt_before: list[str] | None = None):
    """Assemble and compile the per-item pipeline graph."""
    builder = StateGraph(ItemState)
    for name in ["recall", "intake", "redact", "load_context", "interaction",
                 "coverage", "act", "validate", "draft", "dose_check", "finalize"]:
        builder.add_node(name, _bind(getattr(nodes, name), deps))

    builder.add_edge(START, "recall")
    builder.add_edge("recall", "intake")
    builder.add_edge("intake", "redact")
    builder.add_edge("redact", "load_context")
    builder.add_conditional_edges("load_context", _route_after_load,
                                  {"interaction": "interaction", "finalize": "finalize"})
    builder.add_conditional_edges("interaction", _route_after_interaction,
                                  {"coverage": "coverage", "finalize": "finalize"})
    builder.add_conditional_edges("coverage", _route_after_coverage,
                                  {"act": "act", "finalize": "finalize"})
    builder.add_conditional_edges("act", _route_after_act,
                                  {"validate": "validate", "finalize": "finalize"})
    builder.add_conditional_edges("validate", _route_after_validate,
                                  {"draft": "draft", "finalize": "finalize"})
    builder.add_edge("draft", "dose_check")
    builder.add_edge("dose_check", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_before or [])
