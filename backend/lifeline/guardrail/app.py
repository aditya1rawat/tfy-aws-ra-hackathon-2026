"""Deployed guardrail service: the agent's /check engine + the TF Gateway adapter.

Both surfaces wrap the same deterministic interaction engine, so one service
serves both callers (the bridge and the AI Gateway).
"""
from fastapi import FastAPI

from lifeline.guardrail import server, tf_adapter

app = FastAPI(title="Lifeline Guardrail")
# Reuse the already-tested route handlers from the two existing apps.
app.router.routes.extend(server.app.router.routes)
app.router.routes.extend(
    r for r in tf_adapter.app.router.routes
    if getattr(r, "path", None) not in {"/health"}  # avoid a duplicate /health
)


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8010")))
