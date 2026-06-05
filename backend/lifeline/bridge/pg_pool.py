"""Shared Postgres connection-pool builder for the NeonDB-backed stores.

A single long-lived connection breaks against Neon: its pooler drops idle
connections, so the next query raises OperationalError ("SSL connection has been
closed unexpectedly" / "the connection is closed"). A ConnectionPool with
`check=check_connection` revalidates (and transparently reconnects) each
connection when it is borrowed, so handlers always get a live one.

kwargs match the Neon + langgraph PostgresSaver pattern: autocommit (each
statement commits, as the stores expect), prepare_threshold=0 (required on the
PgBouncer-pooled endpoint), dict_row (langgraph requires it; the stores use it).
"""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def make_pool(dsn: str, *, max_size: int = 4) -> ConnectionPool:
    pool = ConnectionPool(
        dsn,
        min_size=1,
        max_size=max_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        check=ConnectionPool.check_connection,
        open=True,
    )
    return pool
