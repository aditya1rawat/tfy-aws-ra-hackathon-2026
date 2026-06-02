from lifeline.data import load_fixture
from lifeline.guardrail.interactions import build_alias_index, check_interactions


def _alias():
    return build_alias_index(load_fixture("medications.json"))


def _rules():
    return load_fixture("interactions.json")


def test_severe_combo_blocks_by_med_id():
    result = check_interactions(["m_warfarin"], "m_ibuprofen", _rules(), _alias())
    assert result["blocked"] is True
    assert result["violations"][0]["severity"] == "severe"


def test_block_is_order_independent():
    a = check_interactions(["m_warfarin"], "m_ibuprofen", _rules(), _alias())
    b = check_interactions(["m_ibuprofen"], "m_warfarin", _rules(), _alias())
    assert a["blocked"] is True and b["blocked"] is True


def test_block_by_brand_name():
    # "Advil" is a brand of ibuprofen; must normalize to generic and still block
    result = check_interactions(["m_warfarin"], "Advil", _rules(), _alias())
    assert result["blocked"] is True


def test_contraindicated_blocks():
    result = check_interactions(["m_sildenafil"], "m_nitroglycerin", _rules(), _alias())
    assert result["blocked"] is True


def test_moderate_does_not_block_but_reports_violation():
    result = check_interactions(["m_lisinopril"], "m_ibuprofen", _rules(), _alias())
    assert result["blocked"] is False
    assert len(result["violations"]) == 1
    assert result["violations"][0]["severity"] == "moderate"


def test_safe_combo_allows_with_no_violations():
    result = check_interactions(["m_metformin"], "m_atorvastatin", _rules(), _alias())
    assert result["blocked"] is False
    assert result["violations"] == []


def test_determinism_over_many_runs():
    for _ in range(100):
        assert check_interactions(["m_warfarin"], "m_ibuprofen", _rules(), _alias())["blocked"] is True
