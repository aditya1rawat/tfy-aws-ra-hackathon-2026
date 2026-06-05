import json
import time

from psycopg_pool import ConnectionPool

from lifeline.bridge.pg_pool import make_pool

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    seq         BIGSERIAL PRIMARY KEY,
    request_id  TEXT UNIQUE NOT NULL,
    patient_id  TEXT,
    med_id      TEXT,
    request_type TEXT,
    state       JSONB NOT NULL,
    decision    TEXT,
    note        TEXT,
    created_at  DOUBLE PRECISION
)
"""


class PostgresRequestStore:
    """NeonDB-backed product request runs. Mirrors RequestStore's interface.

    Borrows a fresh (revalidated) connection per call from a shared pool so an
    idle Neon connection drop never surfaces as a request error.
    """

    def __init__(self, dsn_or_pool):
        self._pool = dsn_or_pool if isinstance(dsn_or_pool, ConnectionPool) else make_pool(dsn_or_pool)
        with self._pool.connection() as conn:
            conn.execute(_SCHEMA)

    def add(self, request_id: str, state: dict) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO requests (request_id, patient_id, med_id, request_type, state, "
                "created_at) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (request_id) DO UPDATE "
                "SET state = EXCLUDED.state",
                (request_id, state.get("patient_id"), state.get("med_id"),
                 state.get("request_type"), json.dumps(state), time.time()),
            )

    def _row_to_rec(self, row: dict) -> dict:
        return {
            "request_id": row["request_id"], "patient_id": row["patient_id"],
            "med_id": row["med_id"], "request_type": row["request_type"],
            "state": row["state"], "decision": row["decision"], "note": row["note"],
            "created_at": row["created_at"],
        }

    def get(self, request_id: str) -> dict:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM requests WHERE request_id=%s", (request_id,)
            ).fetchone()
        if row is None:
            raise KeyError(request_id)
        return self._row_to_rec(row)

    def set_decision(self, request_id: str, *, decision: str, note: str | None,
                     status: str) -> dict:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE requests SET decision=%s, note=%s, "
                "state = jsonb_set(state, '{status}', to_jsonb(%s::text)) WHERE request_id=%s",
                (decision, note, status, request_id),
            )
        return self.get(request_id)

    def list_all(self) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute("SELECT * FROM requests ORDER BY seq DESC").fetchall()
        return [self._row_to_rec(r) for r in rows]

    def list_by_patient(self, patient_id: str) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM requests WHERE patient_id=%s ORDER BY seq DESC", (patient_id,)
            ).fetchall()
        return [self._row_to_rec(r) for r in rows]

    def clear(self) -> int:
        with self._pool.connection() as conn:
            cur = conn.execute("DELETE FROM requests")
            return cur.rowcount
