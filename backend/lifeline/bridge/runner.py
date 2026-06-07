import queue
import threading
from typing import Iterator

from lifeline.agent.graph import build_graph
from lifeline.resilience.context import run_scope

_STREAM_DONE = object()


class AgentRunner:
    """Wrap a compiled graph for interactive runs (sync result or streamed node events)."""

    def __init__(self, deps, checkpointer):
        self._graph = build_graph(deps, checkpointer=checkpointer)

    def run_sync(self, state: dict, *, thread_id: str) -> dict:
        with run_scope(thread_id):
            return self._graph.invoke(state, {"configurable": {"thread_id": thread_id}})

    def stream(self, state: dict, *, thread_id: str, capture: dict | None = None) -> Iterator[dict]:
        """Yield one event per completed node: {node, status, detail}.

        Nodes that don't change status carry the last known one forward, so the
        timeline shows the agent's real state (e.g. in_progress) rather than null.

        If `capture` is given, it is filled with the full terminal state so the
        caller can persist a streamed run. We use LangGraph's combined
        updates+values stream so the terminal state comes straight from the run
        (backend-agnostic — no checkpointer get_state, which varies by saver).

        The graph runs in a single dedicated worker thread that holds `run_scope`
        for the whole run, pushing events to a queue the caller drains. This is
        essential: a StreamingResponse advances the consuming generator across
        threadpool workers with fresh contexts, so a `run_scope` held in the
        generator itself would be lost between nodes — and every resilience beat
        and gateway-telemetry record (keyed by the run-id contextvar) would
        vanish. Running the graph in one thread keeps the contextvar live for the
        entire run.
        """
        config = {"configurable": {"thread_id": thread_id}}
        events: queue.Queue = queue.Queue()
        error: dict = {}

        def drive() -> None:
            last_status = state.get("status")
            try:
                with run_scope(thread_id):
                    for mode, chunk in self._graph.stream(state, config, stream_mode=["updates", "values"]):
                        if mode == "values":
                            if capture is not None:
                                capture.clear()
                                capture.update(chunk)
                            continue
                        for node, update in chunk.items():
                            status = update.get("status")
                            if status is not None:
                                last_status = status
                            audit = update.get("audit") or [{}]
                            events.put({
                                "node": node,
                                "status": last_status,
                                "detail": audit[-1].get("detail"),
                            })
            except Exception as exc:  # surface to the consumer after draining
                error["exc"] = exc
            finally:
                events.put(_STREAM_DONE)

        worker = threading.Thread(target=drive, name=f"agent-stream-{thread_id}", daemon=True)
        worker.start()
        while True:
            item = events.get()
            if item is _STREAM_DONE:
                break
            yield item
        worker.join()
        if "exc" in error:
            raise error["exc"]
