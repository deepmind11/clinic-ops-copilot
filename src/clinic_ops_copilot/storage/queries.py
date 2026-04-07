"""Raw SQL query helpers for the operational FHIR database.

These are the read/write surfaces that the agent tools call into.
Kept as plain functions over psycopg cursors for clarity and audibility.
No ORM. The SQL is what runs.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from clinic_ops_copilot.storage.database import get_cursor

# ---------------------------------------------------------------------------
# Patient lookups
# ---------------------------------------------------------------------------


def find_patient_by_phone(phone: str) -> dict[str, Any] | None:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, family_name, given_name, birth_date, language, phone "
            "FROM patient WHERE phone = %s LIMIT 1",
            (phone,),
        )
        return cur.fetchone()


def find_patient_by_name(family_name: str) -> list[dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, family_name, given_name, birth_date, language, phone "
            "FROM patient WHERE family_name ILIKE %s ORDER BY family_name LIMIT 20",
            (f"%{family_name}%",),
        )
        return list(cur.fetchall())


def get_patient(patient_id: str) -> dict[str, Any] | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM patient WHERE id = %s", (patient_id,))
        return cur.fetchone()


# ---------------------------------------------------------------------------
# Practitioner lookups
# ---------------------------------------------------------------------------


def list_practitioners(specialty: str | None = None) -> list[dict[str, Any]]:
    with get_cursor() as cur:
        if specialty:
            cur.execute(
                "SELECT id, family_name, given_name, specialty FROM practitioner "
                "WHERE active = TRUE AND specialty = %s ORDER BY family_name",
                (specialty,),
            )
        else:
            cur.execute(
                "SELECT id, family_name, given_name, specialty FROM practitioner "
                "WHERE active = TRUE ORDER BY family_name"
            )
        return list(cur.fetchall())


# ---------------------------------------------------------------------------
# Slot + appointment lookups (Scheduler agent surface)
# ---------------------------------------------------------------------------


def find_open_slots(
    practitioner_id: str | None,
    start_date: date,
    end_date: date,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return up to `limit` open slots in the date window.

    If `practitioner_id` is None, returns slots across all active providers.
    """
    end_dt = datetime.combine(end_date, datetime.min.time()) + timedelta(days=1)
    start_dt = datetime.combine(start_date, datetime.min.time())

    with get_cursor() as cur:
        if practitioner_id:
            cur.execute(
                "SELECT s.id, s.practitioner_id, s.start_time, s.end_time, "
                "p.family_name, p.given_name, p.specialty "
                "FROM provider_slot s "
                "JOIN practitioner p ON p.id = s.practitioner_id "
                "WHERE s.booked = FALSE "
                "AND s.start_time >= %s AND s.start_time < %s "
                "AND s.practitioner_id = %s "
                "ORDER BY s.start_time LIMIT %s",
                (start_dt, end_dt, practitioner_id, limit),
            )
        else:
            cur.execute(
                "SELECT s.id, s.practitioner_id, s.start_time, s.end_time, "
                "p.family_name, p.given_name, p.specialty "
                "FROM provider_slot s "
                "JOIN practitioner p ON p.id = s.practitioner_id "
                "WHERE s.booked = FALSE "
                "AND s.start_time >= %s AND s.start_time < %s "
                "ORDER BY s.start_time LIMIT %s",
                (start_dt, end_dt, limit),
            )
        return list(cur.fetchall())


def book_appointment(
    slot_id: str,
    patient_id: str,
    service_code: str,
    description: str,
) -> dict[str, Any]:
    """Atomically book a slot and create an Appointment row.

    Raises ValueError if the slot is already booked.
    """
    appointment_id = f"appt-{slot_id}"
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, practitioner_id, start_time, end_time, booked "
            "FROM provider_slot WHERE id = %s FOR UPDATE",
            (slot_id,),
        )
        slot = cur.fetchone()
        if slot is None:
            raise ValueError(f"slot {slot_id} not found")
        if slot["booked"]:
            raise ValueError(f"slot {slot_id} already booked")

        cur.execute(
            "INSERT INTO appointment "
            "(id, patient_id, practitioner_id, status, service_code, description, "
            "start_time, end_time, resource) "
            "VALUES (%s, %s, %s, 'booked', %s, %s, %s, %s, %s::jsonb) "
            "RETURNING id, patient_id, practitioner_id, start_time, end_time, status",
            (
                appointment_id,
                patient_id,
                slot["practitioner_id"],
                service_code,
                description,
                slot["start_time"],
                slot["end_time"],
                "{}",
            ),
        )
        appt = cur.fetchone()

        cur.execute(
            "UPDATE provider_slot SET booked = TRUE, appointment_id = %s WHERE id = %s",
            (appointment_id, slot_id),
        )

        return dict(appt) if appt else {}


def cancel_appointment(appointment_id: str) -> bool:
    with get_cursor() as cur:
        cur.execute(
            "UPDATE appointment SET status = 'cancelled' WHERE id = %s RETURNING id",
            (appointment_id,),
        )
        if cur.fetchone() is None:
            return False
        cur.execute(
            "UPDATE provider_slot SET booked = FALSE, appointment_id = NULL "
            "WHERE appointment_id = %s",
            (appointment_id,),
        )
        return True


# ---------------------------------------------------------------------------
# Coverage lookups (Eligibility agent surface)
# ---------------------------------------------------------------------------


def lookup_coverage(patient_id: str) -> list[dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, payor, plan_name, status, period_start, period_end "
            "FROM coverage WHERE patient_id = %s ORDER BY period_start DESC",
            (patient_id,),
        )
        return list(cur.fetchall())


def check_coverage_active(coverage_id: str, on_date: date) -> dict[str, Any]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, payor, plan_name, status, period_start, period_end "
            "FROM coverage WHERE id = %s",
            (coverage_id,),
        )
        cov = cur.fetchone()

    if cov is None:
        return {"active": False, "reason": "coverage not found"}

    if cov["status"] != "active":
        return {"active": False, "reason": f"status is {cov['status']}", "coverage": cov}

    if cov["period_start"] and on_date < cov["period_start"]:
        return {"active": False, "reason": "before period_start", "coverage": cov}

    if cov["period_end"] and on_date > cov["period_end"]:
        return {"active": False, "reason": "after period_end (expired)", "coverage": cov}

    return {"active": True, "coverage": cov}
