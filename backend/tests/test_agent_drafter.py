from lifeline.agent.llm import (
    DraftReply, TemplatedDrafter, is_dose_chaos, set_dose_chaos,
)


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


def test_dose_chaos_lever_toggles():
    assert is_dose_chaos() is False
    set_dose_chaos(True)
    assert is_dose_chaos() is True
    set_dose_chaos(False)
    assert is_dose_chaos() is False
