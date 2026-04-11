"""Tool surface for the Onboarding agent.

The Onboarding agent handles new-patient intake — checking whether someone is
already in the system by phone, and creating a new Patient record if not. Once
registered, the patient can immediately be booked by the Scheduler agent or
checked by the Eligibility agent using the returned ``patient_id``.

Tool functions wrap storage queries and return plain dicts so the agent can
render them back to the patient without JSON leaking into the conversation.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from clinic_ops_copilot.storage import queries

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def lookup_patient(query: str) -> dict[str, Any]:
    """Check whether a patient already exists by phone number or family name.

    Call this BEFORE registering a new patient so we don't create duplicates.
    """
    if any(c.isdigit() for c in query):
        normalized = "".join(c for c in query if c.isdigit() or c == "+")
        patient = queries.find_patient_by_phone(normalized)
        if patient:
            return {
                "matches": 1,
                "patients": [
                    {
                        "patient_id": patient["id"],
                        "name": f"{patient['given_name']} {patient['family_name']}",
                        "phone": patient.get("phone"),
                    }
                ],
            }

    name_matches = queries.find_patient_by_name(query)
    return {
        "matches": len(name_matches),
        "patients": [
            {
                "patient_id": p["id"],
                "name": f"{p['given_name']} {p['family_name']}",
                "phone": p.get("phone"),
            }
            for p in name_matches
        ],
    }


def register_patient(
    family_name: str,
    given_name: str,
    phone: str,
    birth_date: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Create a new patient record.

    Validates the inputs, generates a new patient_id, and inserts a FHIR-shaped
    row. Returns ``success=False`` with a clear reason if the input is invalid
    or a patient with the given phone already exists. Input validation runs
    BEFORE any database I/O so bad requests fail fast.
    """
    # --- Step 1: validate inputs (no I/O) ---
    if not family_name or not family_name.strip():
        return {"success": False, "reason": "family_name is required"}
    if not given_name or not given_name.strip():
        return {"success": False, "reason": "given_name is required"}

    normalized_phone = "".join(c for c in phone if c.isdigit() or c == "+")
    if not normalized_phone:
        return {"success": False, "reason": "phone must contain digits"}

    parsed_dob: date | None = None
    if birth_date:
        try:
            parsed_dob = date.fromisoformat(birth_date)
        except ValueError:
            return {
                "success": False,
                "reason": f"birth_date must be ISO format YYYY-MM-DD, got {birth_date!r}",
            }
        today = date.today()
        if parsed_dob > today:
            return {"success": False, "reason": "birth_date cannot be in the future"}
        # Reject obviously bogus ages (>130 years) but allow newborns
        if (today - parsed_dob).days > 130 * 365:
            return {"success": False, "reason": "birth_date is more than 130 years ago"}

    if language not in ("en", "es"):
        language = "en"

    # --- Step 2: duplicate check (DB I/O) ---
    existing = queries.find_patient_by_phone(normalized_phone)
    if existing is not None:
        return {
            "success": False,
            "reason": "patient with this phone number already exists",
            "existing_patient_id": existing["id"],
            "existing_name": f"{existing['given_name']} {existing['family_name']}",
        }

    # --- Step 3: insert ---
    try:
        row = queries.create_patient(
            family_name=family_name.strip(),
            given_name=given_name.strip(),
            phone=normalized_phone,
            birth_date=parsed_dob,
            language=language,
        )
    except Exception as e:
        return {"success": False, "reason": f"database error: {e}"}

    return {
        "success": True,
        "patient_id": row["id"],
        "name": f"{row['given_name']} {row['family_name']}",
        "phone": row.get("phone"),
        "language": row.get("language"),
    }


# ---------------------------------------------------------------------------
# Tool dispatch table + JSON schemas exposed to the LLM
# ---------------------------------------------------------------------------


ONBOARDING_TOOL_FUNCS = {
    "lookup_patient": lookup_patient,
    "register_patient": register_patient,
}


ONBOARDING_TOOLS = [
    {
        "name": "lookup_patient",
        "description": (
            "Check whether a patient already exists by phone number (digits) or "
            "family name (text). ALWAYS call this with the patient's phone before "
            "registering them so you don't create a duplicate."
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
        "name": "register_patient",
        "description": (
            "Create a new patient record. Returns success=False if the phone "
            "number already belongs to an existing patient or if the birth_date "
            "is invalid. Returns the new patient_id on success — the patient can "
            "use it immediately to book appointments or check coverage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "family_name": {
                    "type": "string",
                    "description": "Patient's last name / surname",
                },
                "given_name": {
                    "type": "string",
                    "description": "Patient's first name",
                },
                "phone": {
                    "type": "string",
                    "description": (
                        "Primary phone number. Digits and '+' only; other "
                        "characters are stripped before storage."
                    ),
                },
                "birth_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD). Optional but strongly encouraged.",
                },
                "language": {
                    "type": "string",
                    "enum": ["en", "es"],
                    "description": "Preferred communication language",
                    "default": "en",
                },
            },
            "required": ["family_name", "given_name", "phone"],
        },
    },
]
