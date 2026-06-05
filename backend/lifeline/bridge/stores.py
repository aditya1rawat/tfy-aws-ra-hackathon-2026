"""Pick operational stores by env: SQLite/in-memory locally, Postgres on Neon.

`make_*` map `settings.database_url` to the right backing store. The Postgres
implementations are imported at module level (psycopg is a hard dependency) so
they can be substituted in tests.
"""
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.batch.pg_store import PostgresJobStore
from lifeline.batch.store import JobStore
from lifeline.bridge.pg_request_store import PostgresRequestStore
from lifeline.bridge.request_store import RequestStore


def _is_postgres(dsn: str) -> bool:
    return dsn.startswith("postgres://") or dsn.startswith("postgresql://")


def make_job_store(settings):
    if _is_postgres(settings.database_url):
        return PostgresJobStore(settings.database_url)
    return JobStore("lifeline_jobs.db")


def make_request_store(settings):
    if _is_postgres(settings.database_url):
        return PostgresRequestStore(settings.database_url)
    return RequestStore()


def make_checkpointer(settings):
    if _is_postgres(settings.database_url):
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver

        conn = psycopg.connect(settings.database_url, autocommit=True, prepare_threshold=0)
        saver = PostgresSaver(conn)
        saver.setup()
        return saver
    conn = sqlite3.connect(settings.checkpoint_db_path, check_same_thread=False)
    return SqliteSaver(conn)
