BLOCKING_SEVERITIES = {"severe", "contraindicated"}


def normalize(name: str) -> str:
    return name.strip().lower()


def build_alias_index(medications: list[dict]) -> dict[str, str]:
    """Map every known name (generic, med_id, brand) to its normalized generic name."""
    index: dict[str, str] = {}
    for m in medications:
        generic = normalize(m["generic_name"])
        index[generic] = generic
        index[normalize(m["med_id"])] = generic
        for brand in m.get("brand_names", []):
            index[normalize(brand)] = generic
    return index


def to_generic(name: str, alias_index: dict[str, str]) -> str:
    return alias_index.get(normalize(name), normalize(name))


def check_interactions(existing_meds: list[str], proposed_med: str,
                       ruleset: list[dict], alias_index: dict[str, str]) -> dict:
    """Exhaustively check the proposed med against every existing med.

    Returns {"blocked": bool, "violations": [{"with","severity","reason"}, ...]}.
    Deterministic and complete: every existing/proposed pair is checked against
    every rule, in both orderings.
    """
    proposed = to_generic(proposed_med, alias_index)
    existing = [to_generic(m, alias_index) for m in existing_meds]
    violations = []
    for current in existing:
        for rule in ruleset:
            pair = {normalize(rule["drug_a"]), normalize(rule["drug_b"])}
            if pair == {current, proposed} and current != proposed:
                violations.append({
                    "with": current,
                    "severity": rule["severity"],
                    "reason": rule["reason"],
                })
    blocked = any(v["severity"] in BLOCKING_SEVERITIES for v in violations)
    return {"blocked": blocked, "violations": violations}
