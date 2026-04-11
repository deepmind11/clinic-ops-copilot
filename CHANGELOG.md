# Changelog

All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/) and follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

### Changed

### Fixed

## [0.1.0] - 2026-04-10

### Added

- Repo scaffold and project structure
- Docker Compose for local Postgres (port 5433)
- FHIR R4 Postgres schema: Patient, Appointment, Coverage, Claim, Practitioner, ProviderSlot
- Synthetic FHIR data generator (`scripts/seed.py`) using Faker + `fhir.resources` Pydantic models
- Storage layer: psycopg connection helpers, raw-SQL query module
- SQLite events store with structured per-event logging (trace ID, latency, status)
- **Scheduler agent** — books, reschedules, and cancels appointments; handles double-bookings and provider availability. Tools: `find_open_slots`, `book_appointment`, `cancel_appointment`, `lookup_patient`
- **Eligibility agent** — checks insurance coverage status, expired plans, and prior authorization gaps. Tools: `lookup_coverage`, `check_active_period`, `get_payor_rules`
- **Triage agent** — classifies patient intents and routes to the appropriate downstream agent; handles Spanish / English-Spanish code-switching. Tools: `classify_intent`, `route_to_agent`, `escalate_to_human`
- Agent registry enabling automatic plugin discovery from `plugins/` at startup
- Reference plugin: `plugins/_prior_auth_example.py` (inactive by default; rename to activate)
- `clinicops` CLI with commands: `seed`, `chat`, `logs`, `healthcheck`, `dashboard`, `eval`
- Streamlit observability dashboard: per-agent call counts, p50/p95 latency, tool-call error rate, full trace drill-down
- Eval harness with 20 golden test cases covering scheduling, eligibility, triage, multilingual (Spanish / code-switched), and failure modes
- GitHub Actions CI: Ruff lint + format, Pyright type check, pytest on Python 3.11 and 3.12
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `docs/QUICKSTART.md`, `ROADMAP.md`, `plugins/README.md`
- Provider-agnostic LLM configuration: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` — works with OpenRouter (default), OpenAI, Ollama, and any OpenAI-compatible endpoint

### Known Limitations

- Pyright runs with `continue-on-error` in CI during v0.1
- Loom demo recording pending
- Install from source only (no PyPI release yet)

[Unreleased]: https://github.com/deepmind11/clinic-ops-copilot/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/deepmind11/clinic-ops-copilot/releases/tag/v0.1.0
