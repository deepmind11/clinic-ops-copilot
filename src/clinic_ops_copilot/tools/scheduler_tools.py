"""Tool surface for the Scheduler agent.

Each function corresponds to an Anthropic tool the LLM can call. The tool
schemas are exposed via ``SCHEDULER_TOOLS`` for the agent runner to pass
into the messages.create call.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from clinic_ops_copilot.storage import queries

# ---------------------------------------------------------------------------
# Tool implementations (called by the agent runner after LLM emits tool_use)
# ---------------------------------------------------------------------------


def find_open_slots(
    start_date: str,
    end_date: str,
    practitioner_id: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Find open appointment slots between two dates."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    rows = queries.find_open_slots(practitioner_id, start, end, limit=limit)
    return {
        "count": len(rows),
        "slots": [
            {
                "slot_id": r["id"],
                "practitioner_id": r["practitioner_id"],
                "practitioner_name": f"Dr. {r['family_name']}",
                "specialty": r["specialty"],
                "start_time": r["start_time"].isoformat(),
                "end_time": r["end_time"].isoformat(),
            }
            for r in rows
        ],
    }


def lookup_patient(query: str) -> dict[str, Any]:
    """Find a patient by phone number or family name."""
    if any(c.isdigit() for c in query):
        normalized = "".join(c for c in query if c.isdigit() or c == "+")
        patient = queries.find_patient_by_phone(normalized)
        if patient:
            return {"matches": 1, "patients": [_patient_summary(patient)]}

    name_matches = queries.find_patient_by_name(query)
    return {
        "matches": len(name_matches),
        "patients": [_patient_summary(p) for p in name_matches],
    }


def book_appointment(
    slot_id: str,
    patient_id: str,
    service_code: str,
    description: str,
) -> dict[str, Any]:
    """Book a specific slot for a patient."""
    try:
        appt = queries.book_appointment(slot_id, patient_id, service_code, description)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    return {
        "success": True,
        "appointment_id": appt["id"],
        "status": appt["status"],
        "start_time": appt["start_time"].isoformat() if appt.get("start_time") else None,
    }


def cancel_appointment(appointment_id: str) -> dict[str, Any]:
    ok = queries.cancel_appointment(appointment_id)
    return {"success": ok, "appointment_id": appointment_id}


def _patient_summary(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "patient_id": p["id"],
        "name": f"{p['given_name']} {p['family_name']}",
        "language": p.get("language", "en"),
        "phone": p.get("phone"),
    }


# ---------------------------------------------------------------------------
# Tool dispatch table + JSON schemas exposed to the LLM
# ---------------------------------------------------------------------------


SCHEDULER_TOOL_FUNCS = {
    "find_open_slots": find_open_slots,
    "lookup_patient": lookup_patient,
    "book_appointment": book_appointment,
    "cancel_appointment": cancel_appointment,
}


SCHEDULER_TOOLS = [
    {
        "name": "find_open_slots",
        "description": (
            "Find open appointment slots between two dates. Returns up to `limit` "
            "matching slots, optionally filtered by practitioner_id. Use this BEFORE "
            "calling book_appointment so you have a valid slot_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD) for the start of the search window",
                },
                "end_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD) for the end of the search window",
                },
                "practitioner_id": {
                    "type": "string",
                    "description": "Optional practitioner ID to filter by",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of slots to return",
                    "default": 10,
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "lookup_patient",
        "description": (
            "Find a patient by phone number (digits) or family name (text). "
            "Use this to resolve a patient_id before booking an appointment."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Phone number or family name to search for",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "book_appointment",
        "description": (
            "Book a specific slot for a patient. Returns success=False if the slot "
            "is already booked or does not exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "slot_id": {"type": "string"},
                "patient_id": {"type": "string"},
                "service_code": {
                    "type": "string",
                    "description": "Clinical service code, e.g. 'D1110' for adult prophylaxis",
                },
                "description": {
                    "type": "string",
                    "description": "Short human-readable description of the appointment",
                },
            },
            "required": ["slot_id", "patient_id", "service_code", "description"],
        },
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel an existing appointment by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string"},
            },
            "required": ["appointment_id"],
        },
    },
]
