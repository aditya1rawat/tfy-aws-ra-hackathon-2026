import time
from dataclasses import dataclass

VALID_MODES = {"none", "fail", "slow", "garbage", "ratelimit", "timeout"}


@dataclass
class ChaosConfig:
    mode: str = "none"
    latency_s: float = 0.0


class ToolFailure(Exception):
    """Raised by guard() when a tool is in injected 'fail' mode."""


class RateLimited(ToolFailure):
    """Injected 429-style rate limit (a transient ToolFailure with a precise mode)."""


class ToolTimeout(ToolFailure):
    """Injected timeout (a transient ToolFailure with a precise mode)."""


class ChaosController:
    def __init__(self) -> None:
        self._state: dict[tuple[str, str], ChaosConfig] = {}

    def set(self, server: str, tool: str, mode: str, latency_s: float = 0.0) -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"unknown chaos mode {mode!r}")
        self._state[(server, tool)] = ChaosConfig(mode=mode, latency_s=latency_s)

    def clear(self, server: str, tool: str) -> None:
        self._state.pop((server, tool), None)

    def clear_all(self) -> None:
        self._state.clear()

    def get(self, server: str, tool: str) -> ChaosConfig:
        return self._state.get((server, tool), ChaosConfig())

    def items(self) -> list[tuple[tuple[str, str], ChaosConfig]]:
        """Snapshot of active (server, tool) → config pairs (safe to iterate)."""
        return list(self._state.items())


# module-level singleton shared by every tool
controller = ChaosController()


def guard(server: str, tool: str) -> None:
    """Apply chaos for a tool. Call at the top of every tool function / gateway call."""
    cfg = controller.get(server, tool)
    if cfg.mode == "slow":
        time.sleep(cfg.latency_s)
    elif cfg.mode == "ratelimit":
        raise RateLimited(f"{server}.{tool} rate limited")
    elif cfg.mode == "timeout":
        raise ToolTimeout(f"{server}.{tool} timed out")
    elif cfg.mode == "fail":
        raise ToolFailure(f"{server}.{tool} injected failure")


def should_garble(server: str, tool: str) -> bool:
    """True when a tool should return a malformed payload (bad-intermediate-output chaos)."""
    return controller.get(server, tool).mode == "garbage"
