from lifeline.bridge.names import med_name, patient_name


def test_patient_name_known():
    assert patient_name("p_001") == "Aditya Rawat"


def test_patient_name_unknown_falls_back_to_id():
    assert patient_name("p_999") == "p_999"


def test_med_name_titlecased_generic():
    assert med_name("m_aspirin") == "Aspirin"
    assert med_name("m_warfarin") == "Warfarin"


def test_med_name_unknown_falls_back_to_id():
    assert med_name("m_unknown") == "m_unknown"
