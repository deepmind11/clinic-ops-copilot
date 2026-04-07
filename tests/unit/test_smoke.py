"""Smoke tests verifying the package wires together."""

from __future__ import annotations

import clinic_ops_copilot


def test_version() -> None:
    assert clinic_ops_copilot.__version__ == "0.1.0"


def test_cli_app_loads() -> None:
    from clinic_ops_copilot.cli.main import app

    assert app.info.name == "clinicops"


def test_config_loads() -> None:
    from clinic_ops_copilot.config import settings

    assert settings.anthropic_model.startswith("claude-")
    assert settings.api_port > 0


def test_scheduler_tools_schema() -> None:
    from clinic_ops_copilot.tools.scheduler_tools import (
        SCHEDULER_TOOL_FUNCS,
        SCHEDULER_TOOLS,
    )

    tool_names = {t["name"] for t in SCHEDULER_TOOLS}
    func_names = set(SCHEDULER_TOOL_FUNCS.keys())
    assert tool_names == func_names, "tool schemas and dispatch table must match"
    assert "find_open_slots" in tool_names
    assert "book_appointment" in tool_names
    assert "lookup_patient" in tool_names
    assert "cancel_appointment" in tool_names


def test_scheduler_agent_builds() -> None:
    from clinic_ops_copilot.agents.scheduler import build_scheduler_agent

    agent = build_scheduler_agent()
    assert agent.name == "scheduler"
    assert len(agent.tools) == 4
    assert "lookup_patient" in agent.tool_funcs


def test_events_store_init() -> None:
    """Events DB should initialize and accept a write."""
    import os
    import tempfile

    # Use a temp DB so we don't pollute the dev events.db
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVENTS_DB_PATH"] = os.path.join(tmp, "test_events.db")

        # Reload settings to pick up the env override
        from importlib import reload

        from clinic_ops_copilot import config

        reload(config)
        from clinic_ops_copilot.storage import events

        reload(events)

        events.init_events_db()
        events.record_event(
            trace_id="test-trace",
            agent="scheduler",
            event_type="agent_start",
            status="ok",
            payload={"user": "hello"},
        )
        rows = events.recent_events(agent="scheduler", limit=10)
        assert len(rows) == 1
        assert rows[0]["trace_id"] == "test-trace"
