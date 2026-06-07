import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import new_state
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.bridge.runner import AgentRunner
from lifeline.resilience.context import get_run


def test_run_sync_sets_run_id_during_invoke():
    seen = {}

    class _SpyBackend(InProcessBackend):
        def invoke(self, server, tool, kwargs):
            if (server, tool) == ("interactions", "check_interaction"):
                seen["run"] = get_run()           # captured mid-run
            return super().invoke(server, tool, kwargs)

    deps = Deps(llm=FakeLLM(Intent(patient_id="p_002", request_type="refill", med_id="m_ibuprofen")),
                tools=ToolGateway(_SpyBackend()))
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    runner = AgentRunner(deps, checkpointer=cp)
    state = new_state(item_id="rid-123", patient_id="p_002",
                      request_type="refill", med_id="m_ibuprofen")
    runner.run_sync(state, thread_id="rid-123")
    assert seen["run"] == "rid-123"
    assert get_run() is None                  # reset after
