"""SQLite events store for per-call telemetry.

Decoupled from the operational Postgres database so observability writes
never block the hot path. Single-file SQLite is fine for single-node deploys
and graduates cleanly to ClickHouse or DuckDB at scale.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from clinic_ops_copilot.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    tool_name TEXT,
    latency_ms INTEGER,
    status TEXT NOT NULL,
    payload TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id);
CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);

CREATE TABLE IF NOT EXISTS eval_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    suite TEXT NOT NULL,
    case_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    notes TEXT
);
"""


@contextmanager
def get_events_db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.events_db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_events_db() -> None:
    """Create tables if they don't exist."""
    with get_events_db() as conn:
        conn.executescript(SCHEMA)


def record_event(
    trace_id: str,
    agent: str,
    event_type: str,
    status: str,
    tool_name: str | None = None,
    latency_ms: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append a single event to the store."""
    with get_events_db() as conn:
        conn.execute(
            "INSERT INTO events "
            "(timestamp, trace_id, agent, event_type, tool_name, latency_ms, status, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(UTC).isoformat(),
                trace_id,
                agent,
                event_type,
                tool_name,
                latency_ms,
                status,
                json.dumps(payload, default=str) if payload else None,
            ),
        )


def recent_events(
    agent: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    with get_events_db() as conn:
        if agent and agent != "all":
            cur = conn.execute(
                "SELECT * FROM events WHERE agent = ? ORDER BY id DESC LIMIT ?",
                (agent, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in cur.fetchall()]


def record_eval(suite: str, case_id: str, passed: bool, notes: str | None = None) -> None:
    with get_events_db() as conn:
        conn.execute(
            "INSERT INTO eval_runs (timestamp, suite, case_id, passed, notes) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(UTC).isoformat(), suite, case_id, 1 if passed else 0, notes),
        )
