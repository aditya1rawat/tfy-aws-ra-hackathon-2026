import queue
import threading
from typing import Callable, Iterator

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

    def stream(self, state: dict, *, thread_id: str,
               on_complete: Callable[[dict], None] | None = None) -> Iterator[dict]:
        """Yield one event per completed node: {node, status, detail}.

        Nodes that don't change status carry the last known one forward, so the
        timeline shows the agent's real state (e.g. in_progress) rather than null.

        The graph runs in a single dedicated worker thread that owns the ENTIRE
        run — execution, recording, and persistence — independent of the client
        connection. The thread:

        - holds `run_scope` for the whole run. A StreamingResponse advances the
          consuming generator across threadpool workers with fresh contexts, so a
          `run_scope` held in the generator would be lost between nodes — and
          every resilience beat / gateway-telemetry record (keyed by the run-id
          contextvar) would vanish. One thread keeps the contextvar live.
        - calls `on_complete(terminal_state)` once the graph reaches a terminal
          state, BEFORE signalling done. Because this runs in the worker (not the
          response generator), it always fires even if the browser closes the SSE
          early — so the run is persisted whether or not anyone is still reading.

        Events flow to the caller via a queue purely for cosmetic animation; the
        durable work does not depend on the caller draining it.
        """
        config = {"configurable": {"thread_id": thread_id}}
        events: queue.Queue = queue.Queue()
        error: dict = {}

        def drive() -> None:
            last_status = state.get("status")
            terminal: dict = {}
            try:
                with run_scope(thread_id):
                    for mode, chunk in self._graph.stream(state, config, stream_mode=["updates", "values"]):
                        if mode == "values":
                            terminal = chunk  # full state snapshot; last one wins
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
                    # Terminal reached inside the worker — persist now, regardless
                    # of whether the client is still listening. Best-effort: a
                    # persist hiccup must not crash the run.
                    if on_complete is not None and terminal:
                        try:
                            on_complete(dict(terminal))
                        except Exception:
                            pass
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
