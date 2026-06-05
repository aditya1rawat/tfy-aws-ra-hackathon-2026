from lifeline.agent.deps import local_deps
from lifeline.agent.llm import PatternLLM
from lifeline.agent.memory import NullMemoryStore


def test_local_deps_has_null_memory():
    d = local_deps(PatternLLM())
    assert isinstance(d.memory, NullMemoryStore)
    assert d.rlog is None
