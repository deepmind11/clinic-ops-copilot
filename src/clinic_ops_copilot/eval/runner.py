"""Eval harness runner.

Two execution modes per case:

* ``deterministic`` -- calls a tool function directly (no LLM, no DB) and
  asserts on the structured return. These run in CI without API keys or
  Postgres, and they form the contract layer for the agent's tool surface.

* ``agent`` -- invokes the actual LLM-backed agent (OpenRouter) over its
  tool surface. Requires ``OPENROUTER_API_KEY`` and a seeded Postgres for
  scheduler/eligibility cases. If the prerequisites are missing, agent-mode
  cases are SKIPPED rather than failing, so CI stays green.

Results are written to the SQLite events store via ``record_eval`` so the
Streamlit dashboard can render the pass/fail trend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clinic_ops_copilot.config import settings
from clinic_ops_copilot.storage.events import init_events_db, record_eval

# Tool registry: every deterministic tool an eval case can call
from clinic_ops_copilot.tools.eligibility_tools import (
    check_active_period,
    get_payor_rules,
    lookup_coverage,
)
from clinic_ops_copilot.tools.triage_tools import (
    classify_intent,
    escalate_to_human,
    route_to_agent,
)

DETERMINISTIC_TOOLS = {
    "classify_intent": classify_intent,
    "route_to_agent": route_to_agent,
    "escalate_to_human": escalate_to_human,
    "lookup_coverage": lookup_coverage,
    "check_active_period": check_active_period,
    "get_payor_rules": get_payor_rules,
}

DEFAULT_CASES_PATH = Path(__file__).resolve().parents[3] / "evals" / "golden" / "cases.json"


@dataclass
class CaseResult:
    case_id: str
    tags: list[str]
    mode: str
    passed: bool
    skipped: bool
    detail: str


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or DEFAULT_CASES_PATH
    with p.open() as f:
        suite = json.load(f)
    return suite["cases"]


# ---------------------------------------------------------------------------
# Expectation matchers
# ---------------------------------------------------------------------------


def _match_expected(actual: dict[str, Any], expected: dict[str, Any]) -> tuple[bool, str]:
    """Check that actual matches each expected key. Returns (ok, mismatch_reason)."""
    for key, want in expected.items():
        if key.endswith("_in"):
            real_key = key[: -len("_in")]
            if actual.get(real_key) not in want:
                return False, f"{real_key}={actual.get(real_key)!r} not in {want}"
            continue

        if key.endswith("_contains"):
            real_key = key[: -len("_contains")]
            value = actual.get(real_key, "")
            if not isinstance(value, str) or want.lower() not in value.lower():
                return False, f"{real_key}={value!r} does not contain {want!r}"
            continue

        if key == "tool_calls_any_of":
            calls = actual.get("tool_calls", [])
            seen = {c.get("tool") for c in calls if isinstance(c, dict)}
            if not seen & set(want):
                return False, f"none of {want} were called (saw {sorted(seen)})"
            continue

        if key == "final_text_should_not_contain":
            text = (actual.get("final_text") or "").lower()
            for forbidden in want:
                if forbidden.lower() in text:
                    return False, f"final_text contained forbidden phrase {forbidden!r}"
            continue

        if actual.get(key) != want:
            return False, f"{key}={actual.get(key)!r} != expected {want!r}"

    return True, "ok"


# ---------------------------------------------------------------------------
# Per-mode runners
# ---------------------------------------------------------------------------


def _run_deterministic(case: dict[str, Any]) -> CaseResult:
    tool_name = case["tool"]
    func = DETERMINISTIC_TOOLS.get(tool_name)
    if func is None:
        return CaseResult(
            case_id=case["id"],
            tags=case.get("tags", []),
            mode="deterministic",
            passed=False,
            skipped=False,
            detail=f"unknown tool {tool_name!r}",
        )

    try:
        actual = func(**case["input"])
    except Exception as e:
        return CaseResult(
            case_id=case["id"],
            tags=case.get("tags", []),
            mode="deterministic",
            passed=False,
            skipped=False,
            detail=f"tool raised: {e}",
        )

    ok, why = _match_expected(actual, case["expected"])
    return CaseResult(
        case_id=case["id"],
        tags=case.get("tags", []),
        mode="deterministic",
        passed=ok,
        skipped=False,
        detail=why,
    )


def _build_agent(name: str) -> Any:
    if name == "scheduler":
        from clinic_ops_copilot.agents.scheduler import build_scheduler_agent

        return build_scheduler_agent()
    if name == "eligibility":
        from clinic_ops_copilot.agents.eligibility import build_eligibility_agent

        return build_eligibility_agent()
    if name == "triage":
        from clinic_ops_copilot.agents.triage import build_triage_agent

        return build_triage_agent()
    raise ValueError(f"unknown agent {name!r}")


def _run_agent_case(case: dict[str, Any]) -> CaseResult:
    if not settings.llm_api_key:
        return CaseResult(
            case_id=case["id"],
            tags=case.get("tags", []),
            mode="agent",
            passed=False,
            skipped=True,
            detail="OPENROUTER_API_KEY not set",
        )

    try:
        agent = _build_agent(case["agent"])
        result = agent.run(case["input"])
    except Exception as e:
        return CaseResult(
            case_id=case["id"],
            tags=case.get("tags", []),
            mode="agent",
            passed=False,
            skipped=False,
            detail=f"agent raised: {e}",
        )

    if result.error:
        return CaseResult(
            case_id=case["id"],
            tags=case.get("tags", []),
            mode="agent",
            passed=False,
            skipped=False,
            detail=f"agent error: {result.error}",
        )

    actual = {
        "final_text": result.final_text,
        "tool_calls": result.tool_calls,
    }
    ok, why = _match_expected(actual, case["expected"])
    return CaseResult(
        case_id=case["id"],
        tags=case.get("tags", []),
        mode="agent",
        passed=ok,
        skipped=False,
        detail=why,
    )


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------


def run_suite(
    suite: str = "all",
    cases_path: Path | None = None,
    persist: bool = True,
) -> list[CaseResult]:
    """Run all cases (or a tag-filtered subset) and return per-case results."""
    cases = load_cases(cases_path)
    if suite != "all":
        cases = [c for c in cases if suite in c.get("tags", [])]

    if persist:
        init_events_db()

    results: list[CaseResult] = []
    for case in cases:
        if case["mode"] == "deterministic":
            r = _run_deterministic(case)
        elif case["mode"] == "agent":
            r = _run_agent_case(case)
        else:
            r = CaseResult(
                case_id=case["id"],
                tags=case.get("tags", []),
                mode=case["mode"],
                passed=False,
                skipped=False,
                detail=f"unknown mode {case['mode']!r}",
            )
        results.append(r)

        if persist and not r.skipped:
            record_eval(suite=suite, case_id=r.case_id, passed=r.passed, notes=r.detail)

    return results


def summarize(results: list[CaseResult]) -> dict[str, int]:
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed and not r.skipped),
        "skipped": sum(1 for r in results if r.skipped),
    }
