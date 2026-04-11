# Roadmap

## Phase 1 -- v0.1 (shipped 2026-04-10)

The minimum viable feature set.

- [x] Repo scaffold + project structure
- [x] README, ARCHITECTURE.md, ROADMAP.md, QUICKSTART.md
- [x] `pyproject.toml` with uv, Ruff, Pyright, pytest
- [x] Docker Compose for local Postgres
- [x] Postgres schema (FHIR R4 subset: Patient, Appointment, Coverage, Claim, Practitioner, ProviderSlot)
- [x] Synthetic FHIR data generator (`scripts/seed.py`) using Faker + `fhir.resources` Pydantic models
- [x] Storage layer: psycopg connection helpers, raw-SQL query module
- [x] Events store (SQLite) with structured logging
- [x] Scheduler agent (OpenAI SDK + custom tool-use loop + full observability)
- [x] Eligibility agent (tools + agent)
- [x] Triage agent with Spanish code-switching support
- [x] CLI: `clinicops seed`, `clinicops chat`, `clinicops logs`, `clinicops healthcheck`
- [x] GitHub Actions: lint, format, type check, pytest
- [x] Streamlit observability dashboard
- [x] Eval harness with 20 golden test cases
- [x] Plugin system (drop `.py` files into `plugins/` to add workflows)
- [x] Provider-agnostic LLM config (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`)

## Unreleased -- post-v0.1 on `main`

Shipping continuously since the v0.1 tag. Bundled into the next release.

- [x] **Onboarding sub-agent** — new-patient intake with duplicate detection, input validation, and FHIR-shaped INSERT into the Patient table
- [x] **Agents-as-tools refactor** — single user-facing ClinicOps Assistant; sub-agents are invisible and invoked as `delegate_to_<name>` tool calls. Removes the previously visible triage → scheduler handoff
- [x] **Interactive REPL** with `prompt-toolkit`: persistent history, `ctrl+r` search, autosuggest, up/down arrow recall
- [x] **Streaming responses** — agent output streams token-by-token via the OpenAI SDK streaming API
- [x] **Current datetime injection** into system prompts so agents resolve relative dates without asking
- [x] **Trace propagation via `ContextVar`** so nested delegate calls land under one trace in the events store
- [x] Onboarding agent-mode eval case
- [ ] Loom demo recording

## Phase 2 -- v0.2

Differentiation layer.

- [ ] Fourth Billing/RCM sub-agent (claim status, denial reason classification, eligibility re-check)
- [ ] History summarization / pruning so long REPL sessions don't blow context
- [ ] Cross-session conversation memory (persist the master's history to disk)
- [ ] Per-customer config layer (one config file per "tenant")
- [ ] Live demo recording

## Phase 3 -- Stretch

Future improvements and extensions.

- [ ] Multi-tenant row-level security with Postgres RLS
- [ ] Real EHR integration via OpenEMR FHIR API
- [ ] Eval harness on production traces (replay anonymized real traffic before prompt promotion)
- [ ] Latency-aware routing (cheaper model for high-confidence intents)
- [ ] PHI redaction layer in front of every prompt
- [ ] HL7 v2 ingestion via Mirth Connect adapter
- [ ] Multi-language support beyond Spanish (Mandarin, Vietnamese, Tagalog)
