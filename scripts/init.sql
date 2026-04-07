-- ClinicOps Copilot: Postgres schema (FHIR R4 subset)
--
-- We store FHIR resources as JSONB to keep schema flexibility while extracting
-- a few hot-path columns as indexed scalars for fast operational queries.
-- This mirrors how production healthcare systems hybridize FHIR JSON storage
-- with relational indices.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Practitioners (providers in the clinic)
CREATE TABLE IF NOT EXISTS practitioner (
    id TEXT PRIMARY KEY,
    family_name TEXT NOT NULL,
    given_name TEXT NOT NULL,
    specialty TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    resource JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_practitioner_active ON practitioner(active);

-- Patients
CREATE TABLE IF NOT EXISTS patient (
    id TEXT PRIMARY KEY,
    family_name TEXT NOT NULL,
    given_name TEXT NOT NULL,
    birth_date DATE,
    language TEXT NOT NULL DEFAULT 'en',
    phone TEXT,
    resource JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_patient_family_name ON patient(family_name);
CREATE INDEX IF NOT EXISTS idx_patient_phone ON patient(phone);
CREATE INDEX IF NOT EXISTS idx_patient_language ON patient(language);

-- Coverage (insurance)
CREATE TABLE IF NOT EXISTS coverage (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patient(id) ON DELETE CASCADE,
    payor TEXT NOT NULL,
    plan_name TEXT,
    status TEXT NOT NULL,
    period_start DATE,
    period_end DATE,
    resource JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coverage_patient ON coverage(patient_id);
CREATE INDEX IF NOT EXISTS idx_coverage_status ON coverage(status);
CREATE INDEX IF NOT EXISTS idx_coverage_period ON coverage(period_start, period_end);

-- Appointments
CREATE TABLE IF NOT EXISTS appointment (
    id TEXT PRIMARY KEY,
    patient_id TEXT REFERENCES patient(id) ON DELETE SET NULL,
    practitioner_id TEXT REFERENCES practitioner(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    service_code TEXT,
    description TEXT,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    resource JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_appointment_patient ON appointment(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointment_practitioner ON appointment(practitioner_id);
CREATE INDEX IF NOT EXISTS idx_appointment_start ON appointment(start_time);
CREATE INDEX IF NOT EXISTS idx_appointment_status ON appointment(status);

-- Claims
CREATE TABLE IF NOT EXISTS claim (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patient(id) ON DELETE CASCADE,
    coverage_id TEXT REFERENCES coverage(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    total_amount NUMERIC(10, 2),
    service_date DATE,
    resource JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_claim_patient ON claim(patient_id);
CREATE INDEX IF NOT EXISTS idx_claim_status ON claim(status);

-- Provider available slots (denormalized for fast scheduling lookups)
CREATE TABLE IF NOT EXISTS provider_slot (
    id TEXT PRIMARY KEY,
    practitioner_id TEXT NOT NULL REFERENCES practitioner(id) ON DELETE CASCADE,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    booked BOOLEAN NOT NULL DEFAULT FALSE,
    appointment_id TEXT REFERENCES appointment(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (practitioner_id, start_time)
);

CREATE INDEX IF NOT EXISTS idx_slot_practitioner ON provider_slot(practitioner_id);
CREATE INDEX IF NOT EXISTS idx_slot_start ON provider_slot(start_time);
CREATE INDEX IF NOT EXISTS idx_slot_booked ON provider_slot(booked);
