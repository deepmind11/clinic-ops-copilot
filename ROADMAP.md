# Roadmap

## Phase 1 — v0.1 (in progress, 2026-04-07)

The minimum viable artifact a Forward Deployed Engineer would bring to a customer on day one.

- [x] Repo scaffold + project structure
- [x] README, ARCHITECTURE.md, ROADMAP.md
- [ ] `pyproject.toml` with uv, Ruff, Pyright, pytest
- [ ] Docker Compose for local Postgres
- [ ] FHIR R4 Pydantic models (Patient, Appointment, Coverage, Claim, Practitioner)
- [ ] Synthea integration script (`scripts/generate_synthea.py`)
- [ ] Migration script (`scripts/migrate.py`) loading Synthea output into Postgres
- [ ] Tool surfaces wrapping Postgres queries
- [ ] Scheduler agent (Claude Agent SDK)
- [ ] Eligibility agent
- [ ] Triage agent (with Spanish code-switching support)
- [ ] FastAPI gateway with one POST endpoint per agent
- [ ] Events store (SQLite) with structured logging on every tool call
- [ ] Streamlit observability dashboard
- [ ] CLI (`clinicops seed`, `clinicops serve`, `clinicops dashboard`, `clinicops eval`, `clinicops logs`)
- [ ] Eval harness with 20 golden test cases
- [ ] GitHub Actions: lint, type check, pytest, eval harness on every PR
- [ ] README polish + Loom demo recording

## Phase 2 — v0.2

Differentiation layer. Ships after v0.1 lands.

- [ ] Terraform module: AWS Lambda + RDS Postgres + API Gateway
- [ ] Public AWS-hosted demo URL
- [ ] Fourth Billing/RCM agent (claim status, denial reason classification, eligibility re-check)
- [ ] Loom demo with the live URL
- [ ] Per-customer config layer (one config file per "tenant")

## Phase 3 — Stretch

The "what I would do with more time" list, kept here so reviewers can see the long-range plan.

- [ ] Multi-tenant row-level security with Postgres RLS
- [ ] Real EHR integration via OpenEMR FHIR API
- [ ] Eval harness on production traces (replay anonymized real traffic before prompt promotion)
- [ ] Latency-aware routing (cheaper model for high-confidence intents)
- [ ] PHI redaction layer in front of every prompt
- [ ] HL7 v2 ingestion via Mirth Connect adapter
- [ ] Multi-language support beyond Spanish (Mandarin, Vietnamese, Tagalog)
