import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

_cache: dict[str, object] = {}


def load_fixture(name: str):
    """Load and cache a JSON fixture by filename (e.g. "patients.json")."""
    if name not in _cache:
        with open(FIXTURES_DIR / name) as f:
            _cache[name] = json.load(f)
    return _cache[name]


def reset_cache() -> None:
    """Drop the in-memory fixture cache (test helper)."""
    _cache.clear()
