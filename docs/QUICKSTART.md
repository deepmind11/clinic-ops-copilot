# Quickstart

A full walkthrough from clone to conversation in about 5 minutes.

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** for package management
- **Docker + Docker Compose** (for the local Postgres instance)
- **An API key** for any OpenAI-compatible LLM provider. See `.env.example` for the provider options:
  - OpenRouter (default) — one key, 100+ models
  - OpenAI — direct
  - Ollama — local, no key required, no signup

## Setup

```bash
# Clone
git clone https://github.com/deepmind11/clinic-ops-copilot.git
cd clinic-ops-copilot

# Install dependencies (core + dev extras for tests)
uv sync --all-extras

# Configure your environment
cp .env.example .env
# Edit .env and set LLM_API_KEY — see .env.example for provider options

# Start Postgres
docker compose up -d

# Verify it's healthy
docker compose ps
```

## Generate and Load Synthetic Data

```bash
uv run clinicops seed --patients 1000
```

This generates 1,000 synthetic patients with appointments, coverage records, and FHIR-shaped JSONB resources, then loads them into Postgres. Takes about 30 seconds on a laptop. Use `--patients 100` for a faster dev loop.

## Talk to the Assistant

```bash
uv run clinicops
```

Drops you into an interactive REPL with the ClinicOps Assistant. Try:

```
you ▶ I'm a new patient. My name is Maria Lopez, phone +15551234567, born 1990-04-15
you ▶ Can you book me a cleaning next Tuesday at 2pm?
you ▶ Will my insurance cover it?
```

The assistant handles all three requests in one conversation. You'll see its response stream token-by-token. Behind the scenes it delegates to the Onboarding, Scheduler, and Eligibility sub-agents — but you don't see the handoff.

Features of the REPL:
- **Up/down arrows** — recall previous messages
- **Ctrl+R** — reverse search through history (like bash)
- **Autosuggest** — inline ghost text suggestions from history
- History is persisted to `~/.clinicops_history` across sessions

Type `exit` or press `ctrl+c` to quit.

### One-shot mode (for scripting)

```bash
uv run clinicops chat "I need to book a cleaning tomorrow at 10am for Maria Lopez"
```

Single request, single response, no interactive session. Useful for scripts, CI, or quick tests.

## Open the Observability Dashboard

In a second terminal:

```bash
uv run clinicops dashboard
```

Opens `http://localhost:8501` with:

- Per-agent call counts (last 1h / 24h / 7d / all time)
- p50/p95 latency per agent
- Tool-call error rate per tool
- Recent decisions with full trace expansion — pick a `trace_id` and see the master's delegate calls alongside each sub-agent's nested tool calls, all under the same trace
- Eval harness pass/fail trend

## Run the Eval Harness

```bash
uv run clinicops eval
```

Runs the golden test suite — a mix of deterministic tool tests (no API key required) and agent-mode tests (requires `LLM_API_KEY` and a seeded Postgres). Pass/fail is written to the events store and surfaced in the dashboard.

To run a filtered subset:

```bash
uv run clinicops eval --suite eligibility   # only eligibility-tagged cases
uv run clinicops eval --suite multilingual
```

## Tail Recent Agent Decisions

```bash
uv run clinicops logs --agent scheduler -n 20
```

Dumps the most recent events for an agent directly from the events store, including trace IDs, tool names, latency, and status.

## Healthcheck

```bash
uv run clinicops healthcheck
```

Quick check that Postgres is reachable, the events store is writable, and `LLM_API_KEY` is set.

## Stop Everything

```bash
docker compose down
```

## Next Steps

- [README.md](../README.md) for the project overview and architecture diagram
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) for the full design rationale
- [plugins/README.md](../plugins/README.md) to add your own workflow
- [CONTRIBUTING.md](../CONTRIBUTING.md) to submit a PR
