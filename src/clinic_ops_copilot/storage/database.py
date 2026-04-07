"""Postgres connection helpers.

We use psycopg 3 directly (no ORM in the hot path) for clarity and to make
the SQL queries auditable. Connection pooling is handled by psycopg's pool
module so the FastAPI app reuses connections across requests.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from clinic_ops_copilot.config import settings


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Yield a Postgres connection. Caller commits or rolls back."""
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor() -> Iterator[psycopg.Cursor]:
    """Yield a cursor on a fresh connection. Auto-commits on success."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def healthcheck() -> bool:
    """Return True if the database is reachable."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()
            return row is not None
    except Exception:
        return False
