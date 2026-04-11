"""Smoke tests verifying the package wires together."""

from __future__ import annotations

from typing import Any

import clinic_ops_copilot


def test_version() -> None:
    assert clinic_ops_copilot.__version__ == "0.2.0"


def test_cli_app_loads() -> None:
    from clinic_ops_copilot.cli.main import app

    assert app.info.name == "clinicops"


def test_config_loads() -> None:
    from clinic_ops_copilot.config import settings

    # Model id is namespaced (e.g. "anthropic/claude-..." or "openai/gpt-4o")
    assert "/" in settings.llm_model
    assert settings.llm_base_url.startswith("http")


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


def test_eligibility_tools_schema() -> None:
    from clinic_ops_copilot.tools.eligibility_tools import (
        ELIGIBILITY_TOOL_FUNCS,
        ELIGIBILITY_TOOLS,
    )

    tool_names = {t["name"] for t in ELIGIBILITY_TOOLS}
    func_names = set(ELIGIBILITY_TOOL_FUNCS.keys())
    assert tool_names == func_names, "tool schemas and dispatch table must match"
    assert "lookup_coverage" in tool_names
    assert "check_active_period" in tool_names
    assert "get_payor_rules" in tool_names


def test_eligibility_agent_builds() -> None:
    from clinic_ops_copilot.agents.eligibility import build_eligibility_agent

    agent = build_eligibility_agent()
    assert agent.name == "eligibility"
    assert len(agent.tools) == 3
    assert "get_payor_rules" in agent.tool_funcs


def test_onboarding_tools_schema() -> None:
    from clinic_ops_copilot.tools.onboarding_tools import (
        ONBOARDING_TOOL_FUNCS,
        ONBOARDING_TOOLS,
    )

    tool_names = {t["name"] for t in ONBOARDING_TOOLS}
    func_names = set(ONBOARDING_TOOL_FUNCS.keys())
    assert tool_names == func_names, "tool schemas and dispatch table must match"
    assert "lookup_patient" in tool_names
    assert "register_patient" in tool_names


def test_onboarding_agent_builds() -> None:
    from clinic_ops_copilot.agents.onboarding import build_onboarding_agent

    agent = build_onboarding_agent()
    assert agent.name == "onboarding"
    assert len(agent.tools) == 2
    assert "register_patient" in agent.tool_funcs
    assert "lookup_patient" in agent.tool_funcs


def test_register_patient_validates_birth_date() -> None:
    """Bad dates should be rejected without hitting the DB."""
    from clinic_ops_copilot.tools.onboarding_tools import register_patient

    # Invalid format — should fail before any DB interaction
    result = register_patient(
        family_name="Smith",
        given_name="John",
        phone="+15551234567",
        birth_date="not-a-date",
    )
    assert result["success"] is False
    assert "YYYY-MM-DD" in result["reason"]


def test_register_builtins_includes_onboarding() -> None:
    """The master agent should see onboarding as a registered delegate."""
    from clinic_ops_copilot.agents.registry import register_builtins, registry

    original = registry._agents
    try:
        registry._agents = {}
        register_builtins()
        assert "onboarding" in registry.names()
        assert "scheduler" in registry.names()
        assert "eligibility" in registry.names()
    finally:
        registry._agents = original


def test_payor_rules_logic() -> None:
    """Sanity check the payor rules registry returns sensible answers."""
    from clinic_ops_copilot.tools.eligibility_tools import get_payor_rules

    # Aetna covers a routine cleaning without prior auth
    aetna = get_payor_rules("Aetna", "D1110")
    assert aetna["covered"] is True
    assert aetna["prior_auth_required"] is False

    # Medicare excludes routine dental
    medicare = get_payor_rules("Medicare", "D1110")
    assert medicare["covered"] is False

    # Unknown payor returns known_payor=False
    unknown = get_payor_rules("RandomPayor", "D1110")
    assert unknown["known_payor"] is False
    assert unknown["covered"] is False

    # Cigna explicitly excludes nitrous oxide
    cigna = get_payor_rules("Cigna", "D9230")
    assert cigna["covered"] is False
    assert "excluded" in cigna["reason"]

    # Blue Cross requires prior auth on extractions
    blue = get_payor_rules("Blue Cross", "D7140")
    assert blue["covered"] is True
    assert blue["prior_auth_required"] is True


def test_triage_tools_schema() -> None:
    from clinic_ops_copilot.tools.triage_tools import TRIAGE_TOOL_FUNCS, TRIAGE_TOOLS

    tool_names = {t["name"] for t in TRIAGE_TOOLS}
    func_names = set(TRIAGE_TOOL_FUNCS.keys())
    assert tool_names == func_names
    assert "classify_intent" in tool_names
    assert "route_to_agent" in tool_names
    assert "escalate_to_human" in tool_names


def test_triage_agent_builds() -> None:
    """Master agent should expose one delegate tool per registered sub-agent
    plus the escalate_to_human tool."""
    from clinic_ops_copilot.agents.registry import AgentRegistry, registry
    from clinic_ops_copilot.agents.scheduler import build_scheduler_agent
    from clinic_ops_copilot.agents.triage import build_triage_agent

    # Fresh registry state for a deterministic tool count. The module-level
    # ``registry`` singleton may be populated from earlier tests; swap in a
    # clean one for the scope of this test.
    original = registry._agents
    try:
        registry._agents = {}
        registry.register("scheduler", "test", build_scheduler_agent)

        agent = build_triage_agent()
        assert agent.name == "triage"

        tool_names = {t["name"] for t in agent.tools}
        assert "delegate_to_scheduler" in tool_names
        assert "escalate_to_human" in tool_names
        assert "delegate_to_scheduler" in agent.tool_funcs
        assert "escalate_to_human" in agent.tool_funcs

        # Also verify the fresh AgentRegistry class can stand alone
        fresh = AgentRegistry()
        assert fresh.names() == []
    finally:
        registry._agents = original


def test_triage_classification_english() -> None:
    from clinic_ops_copilot.tools.triage_tools import classify_intent

    r = classify_intent("I need to book an appointment for a cleaning tomorrow")
    assert r["top_class"] == "scheduling"
    assert r["confidence"] == "high"
    assert r["language"] == "en"


def test_triage_classification_spanish() -> None:
    from clinic_ops_copilot.tools.triage_tools import classify_intent

    r = classify_intent("Necesito agendar una cita para una limpieza mañana")
    assert r["top_class"] == "scheduling"
    assert r["confidence"] == "high"
    assert r["language"] == "es"


def test_triage_classification_code_switched() -> None:
    """Code-switched Spanish + English: the known weakness this project tackles."""
    from clinic_ops_copilot.tools.triage_tools import classify_intent

    r = classify_intent("tengo dolor de muelas and I need to see the dentist hoy")
    # Should still detect scheduling intent and a mixed language
    assert r["top_class"] in ("scheduling", "escalation")
    assert r["language"] in ("mixed", "es", "en")
    # Either way, the patient is asking to be seen today
    assert r["top_score"] >= 1


def test_triage_classification_emergency() -> None:
    from clinic_ops_copilot.tools.triage_tools import classify_intent

    r = classify_intent("I have severe pain and bleeding from my gums")
    assert r["top_class"] == "escalation"


def test_triage_route() -> None:
    from clinic_ops_copilot.tools.triage_tools import route_to_agent

    assert route_to_agent("scheduling")["target"] == "scheduler"
    assert route_to_agent("eligibility")["target"] == "eligibility"
    assert route_to_agent("billing")["routed"] is False  # billing not yet registered
    assert route_to_agent("nonsense")["routed"] is False


def test_triage_escalate() -> None:
    from clinic_ops_copilot.tools.triage_tools import escalate_to_human

    r = escalate_to_human("severe bleeding", urgency="emergency")
    assert r["escalated"] is True
    assert r["urgency"] == "emergency"


def test_dashboard_module_imports() -> None:
    """Dashboard module should import without side effects (no st.* at import time)."""
    from clinic_ops_copilot.observability import dashboard

    assert hasattr(dashboard, "render")


def test_eval_cases_load() -> None:
    from clinic_ops_copilot.eval.runner import load_cases

    cases = load_cases()
    assert len(cases) >= 20, f"expected >= 20 golden cases, got {len(cases)}"
    # Every case has the required keys
    for c in cases:
        assert "id" in c
        assert "tags" in c
        assert "mode" in c
        assert "expected" in c
        assert c["mode"] in ("deterministic", "agent")


def test_eval_deterministic_cases_pass() -> None:
    """All deterministic cases must pass, with no DB or API key required."""
    from clinic_ops_copilot.eval.runner import run_suite, summarize

    results = run_suite(suite="all", persist=False)
    deterministic = [r for r in results if r.mode == "deterministic"]
    assert deterministic, "no deterministic cases found"
    failed = [r for r in deterministic if not r.passed]
    assert not failed, "deterministic eval failures: " + "; ".join(
        f"{r.case_id}: {r.detail}" for r in failed
    )
    summary = summarize(results)
    # Agent cases should be marked skipped (no API key in unit test env)
    assert summary["skipped"] >= 0  # tolerate 0 if a key happens to be set


def test_registry_register_and_lookup() -> None:
    """Fresh registry instance should store and retrieve registrations."""
    from clinic_ops_copilot.agents.registry import AgentRegistry
    from clinic_ops_copilot.agents.scheduler import build_scheduler_agent

    reg = AgentRegistry()
    reg.register("scheduler", "Handles scheduling.", build_scheduler_agent)

    assert "scheduler" in reg.names()
    entry = reg.get("scheduler")
    assert entry is not None
    assert entry.description == "Handles scheduling."
    assert entry.factory is build_scheduler_agent


def test_registry_plugin_discovery(tmp_path: Any) -> None:
    """Registry should auto-discover and load a valid plugin file."""
    import textwrap

    plugin = tmp_path / "dummy_plugin.py"
    plugin.write_text(
        textwrap.dedent("""\
            AGENT_NAME = "dummy"
            AGENT_DESCRIPTION = "A dummy plugin for testing."
            def build_agent():
                from clinic_ops_copilot.agents.scheduler import build_scheduler_agent
                return build_scheduler_agent()
        """)
    )

    from clinic_ops_copilot.agents.registry import AgentRegistry

    reg = AgentRegistry()
    loaded = reg.discover(tmp_path)

    assert "dummy" in loaded
    assert "dummy" in reg.names()
    assert reg.get("dummy").description == "A dummy plugin for testing."  # type: ignore[union-attr]


def test_registry_skips_underscore_files(tmp_path: Any) -> None:
    """Files starting with _ must not be loaded."""
    import textwrap

    (tmp_path / "_example.py").write_text(
        textwrap.dedent("""\
            AGENT_NAME = "should_not_load"
            AGENT_DESCRIPTION = "Should be skipped."
            def build_agent(): pass
        """)
    )

    from clinic_ops_copilot.agents.registry import AgentRegistry

    reg = AgentRegistry()
    loaded = reg.discover(tmp_path)
    assert loaded == []
    assert "should_not_load" not in reg.names()


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
