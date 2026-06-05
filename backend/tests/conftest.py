import os

import pytest

# Keep the suite hermetic. The developer's backend/.env is auto-loaded by
# lifeline.config.load_dotenv(), which would leak real deploy values into tests
# (and make /system/state hit live HydraDB, or bind the module-level
# lifeline.bridge.app to live Neon at import). Strip the deploy-only vars so tests
# run in the same clean, offline state CI sees. TEST_DATABASE_URL is left intact —
# the Postgres parity tests opt in through it.
_DEPLOY_ENV = ("DATABASE_URL", "HYDRADB_API_KEY", "HYDRADB_TENANT_ID", "HYDRADB_SUB_TENANT_ID")

# Run at conftest import — before any test module imports lifeline.bridge.app
# (whose module-level `app = _default_app()` would otherwise connect to Neon).
for _var in _DEPLOY_ENV:
    os.environ.pop(_var, None)


@pytest.fixture(autouse=True)
def _clean_deploy_env(monkeypatch):
    for var in _DEPLOY_ENV:
        monkeypatch.delenv(var, raising=False)
    yield
