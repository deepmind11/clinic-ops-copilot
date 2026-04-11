"""
Example plugin: Prior Authorization agent.

HOW TO ACTIVATE
---------------
1. Copy this file without the leading underscore:
       cp _prior_auth_example.py prior_auth.py
2. Fill in the TODO sections to connect to your data source.
3. Run `clinicops chat "..."` — the agent is auto-discovered on startup.

The leading underscore on this file means the registry skips it. Rename to
activate; rename back (or delete) to deactivate. No core code changes needed.

See plugins/README.md for the full plugin contract.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------

AGENT_NAME = "prior_auth"
AGENT_DESCRIPTION = (
    "Checks whether a procedure requires prior authorization and looks up "
    "the status of an existing authorization request."
)

# ---------------------------------------------------------------------------
# Optional: extra keywords that help classify_intent route to this agent.
# These are merged into the built-in keyword table at startup.
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: dict[str, list[str]] = {
    "prior_auth": [
        "prior auth",
        "prior authorization",
        "pre-authorization",
        "pre auth",
        "auth status",
        "authorization status",
        # Spanish
        "autorización previa",
        "preautorización",
        "estado de autorización",
    ]
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Prior Authorization agent for ClinicOps Copilot.

Your job is to determine whether a procedure requires prior authorization from
the patient's insurance and to surface the current authorization status.

You have access to two tools:
- `check_prior_auth_required(patient_id, service_code)` -- returns whether
  prior auth is needed for this patient + service combination
- `lookup_auth_status(patient_id, service_code)` -- returns the status of any
  existing authorization request (approved, pending, denied)

OPERATING RULES:
1. Always call `check_prior_auth_required` first.
2. If prior auth is required, call `lookup_auth_status` to find any existing request.
3. If no authorization exists, advise the caller to submit one with the payor.
4. If an authorization was denied, surface the denial reason and suggest next steps.
5. Be concise. One short paragraph in your final answer.
"""

# ---------------------------------------------------------------------------
# Tool implementations — fill these in to connect to your data source
# ---------------------------------------------------------------------------


def check_prior_auth_required(patient_id: str, service_code: str) -> dict[str, Any]:
    """Return whether prior auth is required for this patient + service."""
    # TODO: query your coverage / payor rules table
    # Example return shape:
    # {"required": True, "payor": "Aetna", "service_code": "D7140"}
    raise NotImplementedError("connect this to your coverage data source")


def lookup_auth_status(patient_id: str, service_code: str) -> dict[str, Any]:
    """Return the current prior auth status for a pending or approved request."""
    # TODO: query your prior auth tracking table
    # Example return shape:
    # {"found": True, "status": "approved", "auth_number": "A-12345", "valid_through": "2026-12-31"}
    # {"found": False}
    raise NotImplementedError("connect this to your prior auth tracking data source")


# ---------------------------------------------------------------------------
# Tool schemas (Anthropic format) + dispatch table
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "check_prior_auth_required",
        "description": "Check whether a service code requires prior authorization for a patient's coverage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient FHIR resource ID",
                },
                "service_code": {
                    "type": "string",
                    "description": "Procedure / service code (e.g. D7140)",
                },
            },
            "required": ["patient_id", "service_code"],
        },
    },
    {
        "name": "lookup_auth_status",
        "description": "Look up the status of an existing prior authorization request.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient FHIR resource ID",
                },
                "service_code": {
                    "type": "string",
                    "description": "Procedure / service code",
                },
            },
            "required": ["patient_id", "service_code"],
        },
    },
]

TOOL_FUNCS = {
    "check_prior_auth_required": check_prior_auth_required,
    "lookup_auth_status": lookup_auth_status,
}

# ---------------------------------------------------------------------------
# Required: build_agent factory
# ---------------------------------------------------------------------------


def build_agent():  # type: ignore[return]
    from clinic_ops_copilot.agents.base import Agent

    return Agent(
        name=AGENT_NAME,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_funcs=TOOL_FUNCS,
    )
