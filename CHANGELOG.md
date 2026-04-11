# Changelog

All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/) and follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Onboarding agent** — new sub-agent that registers first-time patients into the FHIR database. Duplicate-checks by phone, validates birth dates, returns a new `patient_id` the patient can use immediately. Tools: `lookup_patient`, `register_patient`
- **Interactive REPL** — `clinicops` with no subcommand drops into an interactive session with `prompt-toolkit`: persistent history at `~/.clinicops_history`, up/down arrow recall, `ctrl+r` reverse search, inline autosuggest from history
- **Streaming responses** — agents now use the OpenAI SDK's streaming API; text appears token-by-token as the model generates it. Full accumulated text still returned in `result.final_text` for non-streaming callers
- **Current datetime injection** into the Scheduler, Onboarding, and master agent system prompts at build time, so agents resolve relative dates like "next Tuesday" without asking for clarification
- **Trace propagation via `ContextVar`** — master agent sets `current_trace_id` at the start of its run; delegate tools read it when invoking sub-agents so every nested event lands under the same trace in the events store
- **`register_builtins()`** helper in the agent registry, shared by the CLI startup and eval runner as a single source of truth for default agent registration

### Changed

- **Single-chatbot UX (agents-as-tools refactor)** — the patient now talks to one user-facing ClinicOps Assistant. Sub-agents (Onboarding, Scheduler, Eligibility) are exposed to the master as `delegate_to_<name>` tools and invoked as stateless subroutines. The master owns the full conversation; sub-agent handoffs are invisible to the user. Previous design had a visible "→ scheduler" routing step that has been removed
- **Provider-agnostic LLM configuration** — environment variables renamed from `OPENROUTER_*` to `LLM_*` (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`). Works unchanged with OpenRouter (default), OpenAI, Ollama, LM Studio, Groq, Azure OpenAI, and any OpenAI-compatible provider
- **REPL conversation memory** — in-session history passed to the master on every turn via `prior_messages`, so follow-up messages resolve correctly ("Name: Test, phone 1234" after "I need to book a cleaning")
- **Master agent system prompt** — rewritten to explicitly suppress internal routing disclosure ("never say 'routing to scheduler'"). Tool surface now built dynamically from the agent registry at build time instead of hardcoded
- **Dashboard empty-state text** updated to reference current CLI commands (`clinicops`, `clinicops eval`) instead of removed subcommands
- **CLI `chat` subcommand** simplified — delegates directly to the master agent instead of manually orchestrating triage + downstream handoff

### Fixed

- **`register_patient` input validation** runs before any database I/O, so bad inputs (malformed dates, missing names) fail fast with clear error messages without touching Postgres
- **REPL visual affordances** — HTTP request logs from `httpx` suppressed in the REPL so they don't drown out streamed agent output; session boundary made visually distinct with a `rich.Panel` banner and a colored `you ▶` prompt (not mistakable for a shell prompt)

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
