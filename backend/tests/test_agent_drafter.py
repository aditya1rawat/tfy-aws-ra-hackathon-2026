from lifeline.agent.llm import (
    DraftReply, TemplatedDrafter, _guardrail_block_reason, is_dose_chaos, set_dose_chaos,
)


class _FakeBadRequest(Exception):
    """Mimics openai.BadRequestError: carries a structured `body`."""
    def __init__(self, body):
        super().__init__(body.get("message", "bad request"))
        self.body = body


def _guardrail_400_body(message):
    return {
        "message": "Output Guardrail checks failed",
        "error": {"type": "guardrail_checks_failed", "code": "400"},
        "guardrail_checks": {"output_guardrails": [
            {"guardrail_integration": "g/lifeline-dosage", "result": "failed",
             "data": {"guardrailResponse": {"verdict": False, "message": message}}}]},
    }


def teardown_function():
    set_dose_chaos(False)


def test_templated_drafter_uses_prescribed_dose_when_calm():
    d = TemplatedDrafter()
    reply = d.draft("m_lisinopril", prescribed=10, chaos=False)
    assert isinstance(reply, DraftReply)
    assert reply.med_id == "m_lisinopril"
    assert reply.dose_mg == 10
    assert reply.frequency_per_day == 1
    assert "10" in reply.message


def test_templated_drafter_emits_unsafe_dose_under_chaos():
    d = TemplatedDrafter()
    reply = d.draft("m_lisinopril", prescribed=10, chaos=True)
    assert reply.dose_mg == 80   # deliberately over the 40 mg ceiling
    assert "80" in reply.message


def test_guardrail_block_reason_extracts_message_from_body():
    err = _FakeBadRequest(_guardrail_400_body("lisinopril 80.0 mg exceeds max single dose 40 mg"))
    assert _guardrail_block_reason(err) == "lisinopril 80.0 mg exceeds max single dose 40 mg"


def test_guardrail_block_reason_falls_back_to_string_scan():
    assert _guardrail_block_reason(Exception("... guardrail_checks_failed ...")) \
        == "blocked by gateway guardrail"


def test_guardrail_block_reason_none_for_ordinary_error():
    assert _guardrail_block_reason(Exception("connection reset")) is None


def test_dose_chaos_lever_toggles():
    assert is_dose_chaos() is False
    set_dose_chaos(True)
    assert is_dose_chaos() is True
    set_dose_chaos(False)
    assert is_dose_chaos() is False
