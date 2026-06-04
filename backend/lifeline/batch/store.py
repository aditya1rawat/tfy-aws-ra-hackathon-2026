import sqlite3
import time

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
    updated_at   REAL
)
"""

_NONTERMINAL = ("pending", "in_progress")


class JobStore:
    """SQLite-backed batch job table."""

    def __init__(self, db_path: str = ":memory:"):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def seed(self, items: list[dict]) -> None:
        now = time.time()
        self._conn.executemany(
            "INSERT OR IGNORE INTO jobs "
            "(item_id, patient_id, request_type, med_id, status, raw_text, updated_at) "
            "VALUES (:item_id, :patient_id, :request_type, :med_id, 'pending', :raw_text, :updated_at)",
            [{"raw_text": None, **it, "updated_at": now} for it in items],
        )
        self._conn.commit()

    def claim_next(self) -> dict | None:
        # Single atomic statement: claim exactly one pending row so concurrent
        # callers can't grab the same item (SELECT-then-UPDATE would race).
        row = self._conn.execute(
            "UPDATE jobs SET status='in_progress', updated_at=? "
            "WHERE item_id = (SELECT item_id FROM jobs WHERE status='pending' "
            "ORDER BY item_id LIMIT 1) "
            "RETURNING *",
            (time.time(),),
        ).fetchone()
        self._conn.commit()
        if row is None:
            return None
        return dict(row)

    def mark(self, item_id: str, *, status: str, current_node: str | None = None,
             error: str | None = None, model_used: str | None = None) -> None:
        self._conn.execute(
            "UPDATE jobs SET status=?, current_node=?, error=?, model_used=?, updated_at=? "
            "WHERE item_id=?",
            (status, current_node, error, model_used, time.time(), item_id),
        )
        self._conn.commit()

    def get(self, item_id: str) -> dict:
        row = self._conn.execute("SELECT * FROM jobs WHERE item_id=?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return dict(row)

    def list(self, status: str | None = None) -> list[dict]:
        if status is None:
            rows = self._conn.execute("SELECT * FROM jobs ORDER BY item_id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY item_id", (status,)
            ).fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> dict:
        rows = self._conn.execute("SELECT status, COUNT(*) c FROM jobs GROUP BY status").fetchall()
        return {r["status"]: r["c"] for r in rows}

    def model_counts(self) -> dict:
        rows = self._conn.execute(
            "SELECT model_used, COUNT(*) c FROM jobs WHERE model_used IS NOT NULL GROUP BY model_used"
        ).fetchall()
        return {r["model_used"]: r["c"] for r in rows}

    def requeue_nonterminal(self) -> None:
        """Reset pending/in_progress rows to pending (call on worker restart).

        Attempt is unchanged so a crashed item resumes on its existing thread.
        """
        self._conn.execute(
            f"UPDATE jobs SET status='pending' WHERE status IN {_NONTERMINAL}"
        )
        self._conn.commit()

    def requeue(self, statuses: tuple[str, ...] = ("queued",)) -> int:
        """Reset degraded items (default: queued) to pending for a fresh retry and
        bump their attempt, so the worker runs them on a new thread (not a no-op
        resume of the completed degraded run). Returns the number requeued."""
        placeholders = ",".join("?" * len(statuses))
        cur = self._conn.execute(
            f"UPDATE jobs SET status='pending', attempt=attempt+1, updated_at=? "
            f"WHERE status IN ({placeholders})",
            (time.time(), *statuses),
        )
        self._conn.commit()
        return cur.rowcount

    def clear(self) -> int:
        """Wipe the whole queue (demo kill switch). Returns the number removed."""
        cur = self._conn.execute("DELETE FROM jobs")
        self._conn.commit()
        return cur.rowcount
