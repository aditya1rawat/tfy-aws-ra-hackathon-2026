from lifeline.data import load_fixture


def patient_name(patient_id: str) -> str:
    for p in load_fixture("patients.json"):
        if p["patient_id"] == patient_id:
            return p["name"]
    return patient_id


def med_name(med_id: str) -> str:
    for m in load_fixture("medications.json"):
        if m["med_id"] == med_id:
            return m["generic_name"].title()
    return med_id
