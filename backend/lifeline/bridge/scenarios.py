from lifeline.chaos import controller as chaos

# Each scenario is a list of (server, tool, mode, latency_s) operations.
SCENARIOS: dict[str, list[tuple]] = {
    "tool_outage": [("insurer", "submit_prior_auth", "fail", 0.0)],
    "slow_pharmacy": [("pharmacy", "approve_refill", "slow", 3.0)],
    "garbage_insurer": [("insurer", "submit_prior_auth", "garbage", 0.0)],
    "batch_provider_outage": [("chart", "get_patient_chart", "fail", 0.0)],
    "cascade": [
        ("chart", "get_patient_chart", "slow", 1.0),
        ("formulary", "check_coverage", "ratelimit", 0.0),
        ("insurer", "submit_prior_auth", "timeout", 0.0),
    ],
}


def apply_scenario(name: str) -> list[dict]:
    """Apply every chaos op in a named scenario. Returns the applied ops for display."""
    ops = SCENARIOS[name]  # KeyError on unknown scenario
    applied = []
    for server, tool, mode, latency_s in ops:
        chaos.controller.set(server, tool, mode, latency_s=latency_s)
        applied.append({"server": server, "tool": tool, "mode": mode, "latency_s": latency_s})
    return applied
