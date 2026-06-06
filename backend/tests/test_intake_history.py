from lifeline.agent.deps import local_deps
from lifeline.agent.llm import Intent
from lifeline.agent.nodes import intake
from lifeline.agent.state import new_state


class _SpyLLM:
    name = "spy"
    last_model = "spy"

    def __init__(self):
        self.seen_history = None

    def parse_intent(self, text, *, history=""):
        self.seen_history = history
        return Intent(patient_id="p", request_type="refill", med_id="m_aspirin")


def test_intake_forwards_history_to_llm():
    llm = _SpyLLM()
    d = local_deps(llm)
    s = new_state(item_id="i", patient_id="p", request_type="refill", med_id="m_aspirin",
                  raw_text="please refill my usual")
    s["patient_history"] = [{"med": "m_aspirin", "outcome": "escalated", "request_type": "refill"}]
    intake(s, deps=d)
    assert "m_aspirin" in (llm.seen_history or "")
