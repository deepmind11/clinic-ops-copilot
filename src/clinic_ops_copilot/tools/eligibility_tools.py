"""Tool surface for the Eligibility agent.

The Eligibility agent answers the question: "is this patient covered for this
service today?" It calls into the FHIR Coverage table and a small payor-rules
registry to determine active status, period validity, and prior-auth needs.

The payor rules table is kept in-memory here for v0.1. In a real deployment
this would be a Postgres table loaded from each customer's payor contracts.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from clinic_ops_copilot.storage import queries

# ---------------------------------------------------------------------------
# Payor rules registry (in-memory for v0.1)
# ---------------------------------------------------------------------------
# Each entry models the kinds of rules a real payor contract enforces:
#   covered_services: explicit allow-list of CPT/CDT codes
#   prior_auth_required: codes that need prior auth before the visit
#   excluded_services: explicit deny-list (overrides covered)
#
# Service codes used:
#   D1110 - adult prophylaxis (cleaning)
#   D2150 - amalgam two surfaces
#   D7140 - simple extraction
#   D9230 - nitrous oxide sedation
#   99213 - established patient office visit
#   99214 - established patient office visit, moderate complexity

PAYOR_RULES: dict[str, dict[str, Any]] = {
    "Aetna": {
        "covered_services": ["D1110", "D2150", "D7140", "99213", "99214"],
        "prior_auth_required": ["D9230"],
        "excluded_services": [],
    },
    "Blue Cross": {
        "covered_services": ["D1110", "D2150", "99213", "99214"],
        "prior_auth_required": ["D7140", "D9230"],
        "excluded_services": [],
    },
    "Cigna": {
        "covered_services": ["D1110", "D2150", "D7140", "99213", "99214"],
        "prior_auth_required": [],
        "excluded_services": ["D9230"],
    },
    "United Healthcare": {
        "covered_services": ["D1110", "D2150", "D7140", "99213", "99214", "D9230"],
        "prior_auth_required": ["D7140"],
        "excluded_services": [],
    },
    "Kaiser": {
        "covered_services": ["D1110", "D2150", "99213", "99214"],
        "prior_auth_required": [],
        "excluded_services": ["D7140", "D9230"],
    },
    "Medicare": {
        "covered_services": ["99213", "99214"],
        "prior_auth_required": [],
        "excluded_services": ["D1110", "D2150", "D7140", "D9230"],
    },
    "Medicaid": {
        "covered_services": ["D1110", "99213", "99214"],
        "prior_auth_required": ["D2150", "D7140"],
        "excluded_services": ["D9230"],
    },
}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def lookup_coverage(patient_id: str) -> dict[str, Any]:
    """List all coverage records on file for a patient (newest first)."""
    rows = queries.lookup_coverage(patient_id)
    return {
        "count": len(rows),
        "coverages": [
            {
                "coverage_id": r["id"],
                "payor": r["payor"],
                "plan_name": r["plan_name"],
                "status": r["status"],
                "period_start": r["period_start"].isoformat() if r["period_start"] else None,
                "period_end": r["period_end"].isoformat() if r["period_end"] else None,
            }
            for r in rows
        ],
    }


def check_active_period(coverage_id: str, on_date: str) -> dict[str, Any]:
    """Verify a coverage record is active on a specific date."""
    target = date.fromisoformat(on_date)
    result = queries.check_coverage_active(coverage_id, target)
    out: dict[str, Any] = {
        "coverage_id": coverage_id,
        "on_date": on_date,
        "active": result["active"],
    }
    if "reason" in result:
        out["reason"] = result["reason"]
    if result.get("coverage"):
        cov = result["coverage"]
        out["payor"] = cov["payor"]
        out["plan_name"] = cov["plan_name"]
        out["period_start"] = cov["period_start"].isoformat() if cov["period_start"] else None
        out["period_end"] = cov["period_end"].isoformat() if cov["period_end"] else None
    return out


def get_payor_rules(payor: str, service_code: str) -> dict[str, Any]:
    """Look up coverage rules for a payor + service code combination."""
    rules = PAYOR_RULES.get(payor)
    if rules is None:
        return {
            "payor": payor,
            "service_code": service_code,
            "known_payor": False,
            "covered": False,
            "reason": f"payor '{payor}' not in rules registry",
        }

    if service_code in rules["excluded_services"]:
        return {
            "payor": payor,
            "service_code": service_code,
            "known_payor": True,
            "covered": False,
            "reason": "service explicitly excluded by payor",
        }

    needs_pa = service_code in rules["prior_auth_required"]
    if service_code not in rules["covered_services"] and not needs_pa:
        return {
            "payor": payor,
            "service_code": service_code,
            "known_payor": True,
            "covered": False,
            "reason": "service not in payor covered_services list",
        }

    return {
        "payor": payor,
        "service_code": service_code,
        "known_payor": True,
        "covered": True,
        "prior_auth_required": needs_pa,
        "reason": "covered, prior auth required" if needs_pa else "covered",
    }


# ---------------------------------------------------------------------------
# Tool dispatch table + JSON schemas exposed to the LLM
# ---------------------------------------------------------------------------


ELIGIBILITY_TOOL_FUNCS = {
    "lookup_coverage": lookup_coverage,
    "check_active_period": check_active_period,
    "get_payor_rules": get_payor_rules,
}


ELIGIBILITY_TOOLS = [
    {
        "name": "lookup_coverage",
        "description": (
            "List all insurance coverage records on file for a patient, newest first. "
            "Use this first to discover which coverages exist before checking specifics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to look up coverage for",
                }
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "check_active_period",
        "description": (
            "Verify a specific coverage_id is active on a given date. Returns active=False "
            "with a reason if the policy is expired, future-dated, or marked inactive."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "coverage_id": {
                    "type": "string",
                    "description": "Coverage record ID to check",
                },
                "on_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD) to check coverage on",
                },
            },
            "required": ["coverage_id", "on_date"],
        },
    },
    {
        "name": "get_payor_rules",
        "description": (
            "Look up payor coverage rules for a specific service code. Returns whether "
            "the service is covered and whether prior authorization is required."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "payor": {
                    "type": "string",
                    "description": "Payor name (e.g. 'Aetna', 'Blue Cross', 'Medicare')",
                },
                "service_code": {
                    "type": "string",
                    "description": "Service code (CPT or CDT, e.g. 'D1110', '99213')",
                },
            },
            "required": ["payor", "service_code"],
        },
    },
]
