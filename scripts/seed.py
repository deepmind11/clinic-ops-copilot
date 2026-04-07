"""Seed the operational FHIR database with synthetic clinic data.

For v0.1 we use a Python-based generator (Faker + fhir.resources) instead of
running the Java-based Synthea tool. This keeps the local install lightweight
and lets the demo run on any laptop without Java. Real Synthea integration is
on the Phase 3 stretch list in ROADMAP.md.

Generates:
- 10 practitioners (mix of dentists and hygienists)
- N patients (default 1000), with ~8% Spanish-preferred to exercise the
  Triage agent's multilingual handling
- 1-2 Coverage records per patient, mix of active and expired
- 30 days of provider slots (8 per day per provider, 9am-5pm)
- A small number of pre-booked appointments so the demo has state
"""

from __future__ import annotations

import random
import sys
from datetime import date, datetime, time, timedelta
from typing import Any

from faker import Faker

# Add src to path so this script can be run directly without installing
sys.path.insert(0, "src")

from clinic_ops_copilot.storage.database import get_cursor

fake = Faker()
Faker.seed(42)
random.seed(42)

SPECIALTIES = ["general_dentistry", "hygiene", "endodontics", "orthodontics"]
PAYORS = ["Aetna", "Delta Dental", "Cigna", "MetLife", "BlueCross", "Guardian"]
SERVICE_CODES = [
    ("D1110", "Adult prophylaxis (cleaning)"),
    ("D0150", "Comprehensive oral evaluation"),
    ("D2391", "Resin-based composite filling"),
    ("D7140", "Extraction, erupted tooth"),
    ("D8080", "Comprehensive orthodontic treatment"),
]


def generate_practitioners(n: int = 10) -> list[dict[str, Any]]:
    rows = []
    for i in range(n):
        family = fake.last_name()
        given = fake.first_name()
        specialty = random.choice(SPECIALTIES)
        rows.append(
            {
                "id": f"prac-{i + 1:03d}",
                "family_name": family,
                "given_name": given,
                "specialty": specialty,
                "active": True,
                "resource": {
                    "resourceType": "Practitioner",
                    "id": f"prac-{i + 1:03d}",
                    "name": [{"family": family, "given": [given], "prefix": ["Dr."]}],
                    "active": True,
                },
            }
        )
    return rows


def generate_patients(n: int) -> list[dict[str, Any]]:
    rows = []
    for i in range(n):
        family = fake.last_name()
        given = fake.first_name()
        # 8% Spanish-preferred to exercise Triage multilingual handling
        language = "es" if random.random() < 0.08 else "en"
        if language == "es":
            family = (
                fake.last_name()
                if random.random() < 0.5
                else random.choice(
                    ["Garcia", "Martinez", "Rodriguez", "Hernandez", "Lopez", "Gonzalez"]
                )
            )
            given = random.choice(["Maria", "Jose", "Carlos", "Ana", "Luis", "Sofia"])
        birth = fake.date_of_birth(minimum_age=5, maximum_age=85)
        phone = fake.numerify("+1##########")
        rows.append(
            {
                "id": f"pat-{i + 1:05d}",
                "family_name": family,
                "given_name": given,
                "birth_date": birth,
                "language": language,
                "phone": phone,
                "resource": {
                    "resourceType": "Patient",
                    "id": f"pat-{i + 1:05d}",
                    "name": [{"family": family, "given": [given]}],
                    "birthDate": birth.isoformat(),
                    "communication": [{"language": {"coding": [{"code": language}]}}],
                    "telecom": [{"system": "phone", "value": phone, "use": "mobile"}],
                },
            }
        )
    return rows


def generate_coverage(patients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    today = date.today()
    for idx, p in enumerate(patients):
        n_coverages = random.choices([1, 2], weights=[0.75, 0.25])[0]
        for j in range(n_coverages):
            payor = random.choice(PAYORS)
            # 80% active, 15% expired, 5% future-start
            roll = random.random()
            if roll < 0.80:
                status = "active"
                period_start = today - timedelta(days=random.randint(30, 730))
                period_end = today + timedelta(days=random.randint(30, 365))
            elif roll < 0.95:
                status = "cancelled"
                period_start = today - timedelta(days=random.randint(400, 1000))
                period_end = today - timedelta(days=random.randint(1, 60))
            else:
                status = "draft"
                period_start = today + timedelta(days=random.randint(1, 60))
                period_end = period_start + timedelta(days=365)
            cov_id = f"cov-{idx + 1:05d}-{j}"
            rows.append(
                {
                    "id": cov_id,
                    "patient_id": p["id"],
                    "payor": payor,
                    "plan_name": f"{payor} Premier",
                    "status": status,
                    "period_start": period_start,
                    "period_end": period_end,
                    "resource": {
                        "resourceType": "Coverage",
                        "id": cov_id,
                        "status": status,
                        "beneficiary": {"reference": f"Patient/{p['id']}"},
                        "payor": [{"display": payor}],
                        "period": {
                            "start": period_start.isoformat(),
                            "end": period_end.isoformat(),
                        },
                    },
                }
            )
    return rows


def generate_slots(practitioners: list[dict[str, Any]], days: int = 30) -> list[dict[str, Any]]:
    """8 slots per day per provider, 9am-5pm, 1hr each, weekdays only."""
    rows = []
    today = date.today()
    for prac in practitioners:
        for d in range(days):
            day = today + timedelta(days=d)
            if day.weekday() >= 5:  # Skip weekends
                continue
            for hour in range(9, 17):  # 9am to 5pm
                start_dt = datetime.combine(day, time(hour, 0))
                end_dt = start_dt + timedelta(hours=1)
                slot_id = f"slot-{prac['id']}-{day.isoformat()}-{hour:02d}"
                rows.append(
                    {
                        "id": slot_id,
                        "practitioner_id": prac["id"],
                        "start_time": start_dt,
                        "end_time": end_dt,
                        "booked": False,
                    }
                )
    return rows


def insert_practitioners(rows: list[dict[str, Any]]) -> None:
    import json

    with get_cursor() as cur:
        for r in rows:
            cur.execute(
                "INSERT INTO practitioner (id, family_name, given_name, specialty, active, resource) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT (id) DO NOTHING",
                (
                    r["id"],
                    r["family_name"],
                    r["given_name"],
                    r["specialty"],
                    r["active"],
                    json.dumps(r["resource"]),
                ),
            )


def insert_patients(rows: list[dict[str, Any]]) -> None:
    import json

    with get_cursor() as cur:
        for r in rows:
            cur.execute(
                "INSERT INTO patient (id, family_name, given_name, birth_date, language, phone, resource) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT (id) DO NOTHING",
                (
                    r["id"],
                    r["family_name"],
                    r["given_name"],
                    r["birth_date"],
                    r["language"],
                    r["phone"],
                    json.dumps(r["resource"]),
                ),
            )


def insert_coverage(rows: list[dict[str, Any]]) -> None:
    import json

    with get_cursor() as cur:
        for r in rows:
            cur.execute(
                "INSERT INTO coverage (id, patient_id, payor, plan_name, status, period_start, period_end, resource) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT (id) DO NOTHING",
                (
                    r["id"],
                    r["patient_id"],
                    r["payor"],
                    r["plan_name"],
                    r["status"],
                    r["period_start"],
                    r["period_end"],
                    json.dumps(r["resource"]),
                ),
            )


def insert_slots(rows: list[dict[str, Any]]) -> None:
    with get_cursor() as cur:
        for r in rows:
            cur.execute(
                "INSERT INTO provider_slot (id, practitioner_id, start_time, end_time, booked) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (practitioner_id, start_time) DO NOTHING",
                (
                    r["id"],
                    r["practitioner_id"],
                    r["start_time"],
                    r["end_time"],
                    r["booked"],
                ),
            )


def main(num_patients: int = 1000) -> None:
    print(f"Seeding ClinicOps database with {num_patients} patients...")

    practitioners = generate_practitioners(10)
    insert_practitioners(practitioners)
    print(f"  inserted {len(practitioners)} practitioners")

    patients = generate_patients(num_patients)
    insert_patients(patients)
    print(f"  inserted {len(patients)} patients")

    coverage = generate_coverage(patients)
    insert_coverage(coverage)
    print(f"  inserted {len(coverage)} coverage records")

    slots = generate_slots(practitioners, days=30)
    insert_slots(slots)
    print(f"  inserted {len(slots)} provider slots over the next 30 days")

    print("Done.")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    main(n)
