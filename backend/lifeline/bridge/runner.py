from typing import Iterator

from lifeline.agent.graph import build_graph
from lifeline.resilience.context import run_scope


class AgentRunner:
    """Wrap a compiled graph for interactive runs (sync result or streamed node events)."""

    def __init__(self, deps, checkpointer):
        self._graph = build_graph(deps, checkpointer=checkpointer)

    def run_sync(self, state: dict, *, thread_id: str) -> dict:
        with run_scope(thread_id):
            return self._graph.invoke(state, {"configurable": {"thread_id": thread_id}})

    def stream(self, state: dict, *, thread_id: str) -> Iterator[dict]:
        """Yield one event per completed node: {node, status, detail}.

        Nodes that don't change status carry the last known one forward, so the
        timeline shows the agent's real state (e.g. in_progress) rather than null.
        """
        config = {"configurable": {"thread_id": thread_id}}
        last_status = state.get("status")
        with run_scope(thread_id):
            for chunk in self._graph.stream(state, config):
                for node, update in chunk.items():
                    status = update.get("status")
                    if status is not None:
                        last_status = status
                    audit = update.get("audit") or [{}]
                    yield {
                        "node": node,
                        "status": last_status,
                        "detail": audit[-1].get("detail"),
                    }
