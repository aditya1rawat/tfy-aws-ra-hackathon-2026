import time

import psycopg
from psycopg.rows import dict_row

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    item_id      TEXT PRIMARY KEY,
    patient_id   TEXT NOT NULL,
    request_type TEXT NOT NULL,
    med_id       TEXT NOT NULL,
    status       TEXT NOT NULL,
    current_node TEXT,
    error        TEXT,
    model_used   TEXT,
    raw_text     TEXT,
    attempt      INTEGER NOT NULL DEFAULT 0,
    updated_at   DOUBLE PRECISION
)
"""

_NONTERMINAL = ("pending", "in_progress")


class PostgresJobStore:
    """NeonDB-backed batch job table. Mirrors batch.store.JobStore's interface."""

    def __init__(self, dsn: str):
        # autocommit + dict rows; prepare_threshold=0 keeps Neon's pooled conns happy.
        self._conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row,
                                     prepare_threshold=0)
        self._conn.execute(_SCHEMA)

    def seed(self, items: list[dict]) -> None:
        now = time.time()
        with self._conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO jobs "
                "(item_id, patient_id, request_type, med_id, status, raw_text, updated_at) "
                "VALUES (%(item_id)s, %(patient_id)s, %(request_type)s, %(med_id)s, "
                "'pending', %(raw_text)s, %(updated_at)s) ON CONFLICT (item_id) DO NOTHING",
                [{"raw_text": None, **it, "updated_at": now} for it in items],
            )

    def claim_next(self) -> dict | None:
        row = self._conn.execute(
            "UPDATE jobs SET status='in_progress', updated_at=%s "
            "WHERE item_id = (SELECT item_id FROM jobs WHERE status='pending' "
            "ORDER BY item_id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *",
            (time.time(),),
        ).fetchone()
        return row

    def mark(self, item_id: str, *, status: str, current_node: str | None = None,
             error: str | None = None, model_used: str | None = None) -> None:
        self._conn.execute(
            "UPDATE jobs SET status=%s, current_node=%s, error=%s, model_used=%s, "
            "updated_at=%s WHERE item_id=%s",
            (status, current_node, error, model_used, time.time(), item_id),
        )

    def get(self, item_id: str) -> dict:
        row = self._conn.execute("SELECT * FROM jobs WHERE item_id=%s", (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return row

    def list(self, status: str | None = None) -> list[dict]:
        if status is None:
            return self._conn.execute("SELECT * FROM jobs ORDER BY item_id").fetchall()
        return self._conn.execute(
            "SELECT * FROM jobs WHERE status=%s ORDER BY item_id", (status,)
        ).fetchall()

    def counts(self) -> dict:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) c FROM jobs GROUP BY status"
        ).fetchall()
        return {r["status"]: r["c"] for r in rows}

    def model_counts(self) -> dict:
        rows = self._conn.execute(
            "SELECT model_used, COUNT(*) c FROM jobs WHERE model_used IS NOT NULL "
            "GROUP BY model_used"
        ).fetchall()
        return {r["model_used"]: r["c"] for r in rows}

    def requeue_nonterminal(self) -> None:
        self._conn.execute(
            "UPDATE jobs SET status='pending' WHERE status = ANY(%s)", (list(_NONTERMINAL),)
        )

    def requeue(self, statuses: tuple[str, ...] = ("queued",)) -> int:
        cur = self._conn.execute(
            "UPDATE jobs SET status='pending', attempt=attempt+1, updated_at=%s "
            "WHERE status = ANY(%s)",
            (time.time(), list(statuses)),
        )
        return cur.rowcount

    def clear(self) -> int:
        cur = self._conn.execute("DELETE FROM jobs")
        return cur.rowcount
