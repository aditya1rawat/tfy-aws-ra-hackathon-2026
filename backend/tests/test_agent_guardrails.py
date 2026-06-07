from lifeline.agent.guardrails import (
    InProcessInteractionGuardrail, redact_phi, validate_output,
)


def test_redact_phi_masks_ssn_and_dob():
    out = redact_phi("SSN 123-45-6789 DOB 1958-03-12 for Maria")
    assert "123-45-6789" not in out
    assert "1958-03-12" not in out
    assert "[REDACTED]" in out


def test_redact_phi_passthrough_when_clean():
    assert redact_phi("refill warfarin") == "refill warfarin"


def test_validate_output_accepts_expected_shape():
    assert validate_output({"refill_id": "rx_1", "status": "approved"}, ["refill_id", "status"]) is True


def test_validate_output_rejects_garbage():
    assert validate_output({"ok": True}, ["refill_id", "status"]) is False
    assert validate_output("not-a-dict", ["status"]) is False


def test_inprocess_guardrail_blocks_dangerous_combo():
    g = InProcessInteractionGuardrail()
    out = g.check(["m_warfarin"], "m_ibuprofen")
    assert out["decision"] == "block"
    assert out["violations"][0]["severity"] == "severe"


def test_inprocess_guardrail_allows_safe_combo():
    g = InProcessInteractionGuardrail()
    out = g.check(["m_metformin"], "m_atorvastatin")
    assert out["decision"] == "allow"
    assert out["violations"] == []
