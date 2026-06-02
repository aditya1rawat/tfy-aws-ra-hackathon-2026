from typing import Iterator

from lifeline.agent.graph import build_graph


class AgentRunner:
    """Wrap a compiled graph for interactive runs (sync result or streamed node events)."""

    def __init__(self, deps, checkpointer):
        self._graph = build_graph(deps, checkpointer=checkpointer)

    def run_sync(self, state: dict, *, thread_id: str) -> dict:
        return self._graph.invoke(state, {"configurable": {"thread_id": thread_id}})

    def stream(self, state: dict, *, thread_id: str) -> Iterator[dict]:
        """Yield one event per completed node: {node, status, detail}."""
        config = {"configurable": {"thread_id": thread_id}}
        for chunk in self._graph.stream(state, config):
            for node, update in chunk.items():
                audit = update.get("audit") or [{}]
                yield {
                    "node": node,
                    "status": update.get("status"),
                    "detail": audit[-1].get("detail"),
                }
