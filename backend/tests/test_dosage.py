from lifeline.agent.dosage import check_dose


def test_allows_dose_within_ceiling_and_matching_prescribed():
    out = check_dose("m_lisinopril", 10, 1, prescribed=10)
    assert out["decision"] == "allow"


def test_blocks_when_single_dose_exceeds_ceiling():
    out = check_dose("m_lisinopril", 80, 1, prescribed=10)
    assert out["decision"] == "block"
    assert "80" in out["reason"] and "lisinopril" in out["reason"].lower()


def test_blocks_when_daily_total_exceeds_max():
    # 30 mg x 3 = 90 mg/day > 80 mg max_daily, even though 30 < max_single 40
    out = check_dose("m_lisinopril", 30, 3, prescribed=10)
    assert out["decision"] == "block"
    assert "daily" in out["reason"].lower()


def test_blocks_when_dose_mismatches_prescribed():
    out = check_dose("m_lisinopril", 20, 1, prescribed=10)
    assert out["decision"] == "block"
    assert "prescribed" in out["reason"].lower()


def test_allows_when_no_reference_data_for_med():
    # unknown/unpriced med → fail open (allow); the app never had a ceiling to enforce
    out = check_dose("m_sildenafil", 200, 1, prescribed=None)
    assert out["decision"] == "allow"
