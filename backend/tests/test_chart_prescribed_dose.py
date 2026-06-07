from lifeline.mcp_servers.chart import get_patient_chart


def test_chart_exposes_prescribed_dose_for_lisinopril():
    chart = get_patient_chart("p_001")
    assert chart["prescribed_doses"]["m_lisinopril"] == 10
