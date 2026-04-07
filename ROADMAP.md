# Roadmap

## Phase 1 -- v0.1 (in progress, 2026-04-07)

The minimum viable artifact a Forward Deployed Engineer would bring to a customer on day one.

- [x] Repo scaffold + project structure
- [x] README, ARCHITECTURE.md, ROADMAP.md, QUICKSTART.md
- [x] `pyproject.toml` with uv, Ruff, Pyright, pytest
- [x] Docker Compose for local Postgres
- [x] Postgres schema (FHIR R4 subset: Patient, Appointment, Coverage, Claim, Practitioner, ProviderSlot)
- [x] Synthetic FHIR data generator (`scripts/seed.py`) using Faker + fhir.resources Pydantic models
- [x] Storage layer: psycopg connection helpers, raw-SQL query module
- [x] Events store (SQLite) with structured logging
- [x] Tool surfaces for Scheduler agent
- [x] Scheduler agent (Anthropic SDK with tool-use loop, full observability)
- [x] FastAPI gateway with `/agents/scheduler` endpoint
- [x] CLI (`clinicops seed`, `clinicops serve`, `clinicops logs`, `clinicops healthcheck`)
- [x] Smoke tests passing (6/6)
- [x] GitHub Actions: lint, format, type check, pytest
- [x] Eligibility agent (tools + agent + endpoint)
- [x] Triage agent (tools + agent + endpoint, with Spanish code-switching support)
- [x] Streamlit observability dashboard
- [x] Eval harness with 20 golden test cases
- [ ] Loom demo recording

## Phase 2 -- v0.2

Differentiation layer. Ships after v0.1 lands.

- [ ] Terraform module: AWS Lambda + RDS Postgres + API Gateway
- [ ] Public AWS-hosted demo URL
- [ ] Fourth Billing/RCM agent (claim status, denial reason classification, eligibility re-check)
- [ ] Loom demo with the live URL
- [ ] Per-customer config layer (one config file per "tenant")

## Phase 3 -- Stretch

The "what I would do with more time" list, kept here so reviewers can see the long-range plan.

- [ ] Multi-tenant row-level security with Postgres RLS
- [ ] Real EHR integration via OpenEMR FHIR API
- [ ] Eval harness on production traces (replay anonymized real traffic before prompt promotion)
- [ ] Latency-aware routing (cheaper model for high-confidence intents)
- [ ] PHI redaction layer in front of every prompt
- [ ] HL7 v2 ingestion via Mirth Connect adapter
- [ ] Multi-language support beyond Spanish (Mandarin, Vietnamese, Tagalog)
