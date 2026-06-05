import time

from psycopg_pool import ConnectionPool

from lifeline.bridge.pg_pool import make_pool

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
    """NeonDB-backed batch job table. Mirrors batch.store.JobStore's interface.

    Borrows a fresh (revalidated) connection per call from a shared pool, so an
    idle Neon connection drop never surfaces as a request error.
    """

    def __init__(self, dsn_or_pool):
        self._pool = dsn_or_pool if isinstance(dsn_or_pool, ConnectionPool) else make_pool(dsn_or_pool)
        with self._pool.connection() as conn:
            conn.execute(_SCHEMA)

    def seed(self, items: list[dict]) -> None:
        now = time.time()
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO jobs "
                "(item_id, patient_id, request_type, med_id, status, raw_text, updated_at) "
                "VALUES (%(item_id)s, %(patient_id)s, %(request_type)s, %(med_id)s, "
                "'pending', %(raw_text)s, %(updated_at)s) ON CONFLICT (item_id) DO NOTHING",
                [{"raw_text": None, **it, "updated_at": now} for it in items],
            )

    def claim_next(self) -> dict | None:
        with self._pool.connection() as conn:
            return conn.execute(
                "UPDATE jobs SET status='in_progress', updated_at=%s "
                "WHERE item_id = (SELECT item_id FROM jobs WHERE status='pending' "
                "ORDER BY item_id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *",
                (time.time(),),
            ).fetchone()

    def mark(self, item_id: str, *, status: str, current_node: str | None = None,
             error: str | None = None, model_used: str | None = None) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE jobs SET status=%s, current_node=%s, error=%s, model_used=%s, "
                "updated_at=%s WHERE item_id=%s",
                (status, current_node, error, model_used, time.time(), item_id),
            )

    def get(self, item_id: str) -> dict:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE item_id=%s", (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return row

    def list(self, status: str | None = None) -> list[dict]:
        with self._pool.connection() as conn:
            if status is None:
                return conn.execute("SELECT * FROM jobs ORDER BY item_id").fetchall()
            return conn.execute(
                "SELECT * FROM jobs WHERE status=%s ORDER BY item_id", (status,)
            ).fetchall()

    def counts(self) -> dict:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) c FROM jobs GROUP BY status"
            ).fetchall()
        return {r["status"]: r["c"] for r in rows}

    def model_counts(self) -> dict:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT model_used, COUNT(*) c FROM jobs WHERE model_used IS NOT NULL "
                "GROUP BY model_used"
            ).fetchall()
        return {r["model_used"]: r["c"] for r in rows}

    def requeue_nonterminal(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE jobs SET status='pending' WHERE status = ANY(%s)", (list(_NONTERMINAL),)
            )

    def requeue(self, statuses: tuple[str, ...] = ("queued",)) -> int:
        with self._pool.connection() as conn:
            cur = conn.execute(
                "UPDATE jobs SET status='pending', attempt=attempt+1, updated_at=%s "
                "WHERE status = ANY(%s)",
                (time.time(), list(statuses)),
            )
            return cur.rowcount

    def clear(self) -> int:
        with self._pool.connection() as conn:
            cur = conn.execute("DELETE FROM jobs")
            return cur.rowcount
