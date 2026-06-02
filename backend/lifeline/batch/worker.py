from lifeline.agent.graph import build_graph
from lifeline.agent.state import new_state
from lifeline.batch.store import JobStore


class BatchWorker:
    """Run queued items through the agent graph, one per item_id thread."""

    def __init__(self, store: JobStore, deps, checkpointer):
        self._store = store
        self._graph = build_graph(deps, checkpointer=checkpointer)

    def run_item(self, item: dict) -> dict:
        state = new_state(
            item_id=item["item_id"], patient_id=item["patient_id"],
            request_type=item["request_type"], med_id=item["med_id"],
        )
        out = self._graph.invoke(state, {"configurable": {"thread_id": item["item_id"]}})
        self._store.mark(
            item["item_id"], status=out["status"], current_node=out.get("current_node"),
            error=out.get("error"), model_used=out.get("model_used"),
        )
        return out

    def run_all(self, limit: int | None = None) -> dict:
        """Process pending items until exhausted or `limit` items handled. Returns status counts."""
        processed = 0
        while limit is None or processed < limit:
            item = self._store.claim_next()
            if item is None:
                break
            self.run_item(item)
            processed += 1
        return self._store.counts()
