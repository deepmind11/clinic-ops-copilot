"""Structured logging and trace_id management.

We use structlog to keep log records as machine-parseable dicts. Every
agent call generates a trace_id that propagates through tool calls and
lands in the events store, so the dashboard can show the full chain.
"""

from __future__ import annotations

import logging
import sys
import uuid

import structlog


def new_trace_id() -> str:
    """Generate a fresh trace_id for an incoming agent request."""
    return f"trace-{uuid.uuid4().hex[:12]}"


def configure_logging(level: str = "INFO") -> None:
    """One-time logging setup. Call from CLI/server entry points."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
