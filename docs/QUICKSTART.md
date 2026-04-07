# Quickstart

> **Status:** This walkthrough describes the v0.1 target experience. The CLI commands exist as scaffolding (`TODO` placeholders) at this stage. They are being filled in over the next few days.

## Prerequisites

- Python 3.11+
- Docker + Docker Compose
- An Anthropic API key (`ANTHROPIC_API_KEY` env var)
- [uv](https://github.com/astral-sh/uv) for package management

## Setup

```bash
# Clone
git clone https://github.com/deepmind11/clinic-ops-copilot.git
cd clinic-ops-copilot

# Install dependencies
uv sync

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Start Postgres
docker compose up -d

# Wait for healthy
docker compose ps
```

## Generate and Load Synthetic Data

```bash
clinicops seed --patients 1000
```

This downloads Synthea, generates 1000 synthetic patients with appointments and coverage, and loads them into Postgres via the migration script. Takes about 2 minutes on a laptop.

## Run the Agents

```bash
clinicops serve
```

Starts the FastAPI gateway on `http://localhost:8000`. Each agent is exposed at:

- `POST http://localhost:8000/agents/scheduler`
- `POST http://localhost:8000/agents/eligibility`
- `POST http://localhost:8000/agents/triage`

Try a request:

```bash
curl -X POST http://localhost:8000/agents/triage \
  -H "Content-Type: application/json" \
  -d '{"intent": "tengo dolor de muelas y necesito ver al dentista hoy"}'
```

## Open the Observability Dashboard

In a second terminal:

```bash
clinicops dashboard
```

Opens `http://localhost:8501` with per-agent call counts, latency percentiles, error rates, and a recent-decisions feed.

## Run the Eval Harness

```bash
clinicops eval
```

Runs all 20 golden test cases. Pass/fail is written to the events store and surfaced in the dashboard.

To run a single suite:

```bash
clinicops eval --suite multilingual
```

## Tail Recent Agent Decisions

```bash
clinicops logs --agent scheduler --since 1h
```

## Stop Everything

```bash
docker compose down
```
