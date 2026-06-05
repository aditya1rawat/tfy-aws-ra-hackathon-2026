from types import SimpleNamespace

from lifeline.agent.guardrails import HttpInteractionGuardrail, InProcessInteractionGuardrail
from lifeline.bridge.app import _select_guardrail


def _settings(use_tf, guardrail_url="http://gr:8010"):
    return SimpleNamespace(use_tf=use_tf, guardrail_url=guardrail_url)


def test_offline_uses_in_process():
    g = _select_guardrail(_settings(use_tf=False))
    assert isinstance(g, InProcessInteractionGuardrail)


def test_tf_uses_http_guardrail_at_url():
    g = _select_guardrail(_settings(use_tf=True, guardrail_url="http://gr:8010"))
    assert isinstance(g, HttpInteractionGuardrail)
    assert g._base_url == "http://gr:8010"
