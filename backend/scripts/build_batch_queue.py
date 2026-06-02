import itertools
import json
from pathlib import Path

PATIENTS = ["p_001", "p_002", "p_003"]
REQUEST_TYPES = ["refill", "prior_auth", "benefit"]
MEDS = ["m_ibuprofen", "m_adalimumab", "m_atorvastatin", "m_metformin", "m_sildenafil"]


def build(n: int = 200) -> list[dict]:
    """Deterministically generate n pending batch items by cycling combinations."""
    combos = [(p, t, m) for p in PATIENTS for t in REQUEST_TYPES for m in MEDS]
    cycle = itertools.cycle(combos)
    items = []
    for i in range(1, n + 1):
        patient_id, request_type, med_id = next(cycle)
        items.append({
            "item_id": f"item_{i:04d}",
            "patient_id": patient_id,
            "request_type": request_type,
            "med_id": med_id,
            "status": "pending",
        })
    return items


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "lifeline" / "fixtures" / "batch_queue.json"
    out.write_text(json.dumps(build(), indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
