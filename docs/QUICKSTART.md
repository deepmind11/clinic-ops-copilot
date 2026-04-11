# Quickstart

> **Status:** This walkthrough describes the v0.1 target experience. The CLI commands exist as scaffolding (`TODO` placeholders) at this stage. They are being filled in over the next few days.

## Prerequisites

- Python 3.11+
- Docker + Docker Compose
- An OpenRouter API key (`OPENROUTER_API_KEY` env var). The project talks to OpenRouter via the OpenAI SDK and defaults to `anthropic/claude-sonnet-4.5`.
- [uv](https://github.com/astral-sh/uv) for package management

## Setup

```bash
# Clone
git clone https://github.com/deepmind11/clinic-ops-copilot.git
cd clinic-ops-copilot

# Install dependencies
uv sync

# Set your OpenRouter API key (single LLM provider; OpenAI-compatible API)
export OPENROUTER_API_KEY=sk-or-v1-...
# Optional overrides:
# export OPENROUTER_MODEL=anthropic/claude-sonnet-4.5
# export OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

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
clinicops chat "tengo dolor de muelas y necesito ver al dentista hoy"
```

Triage classifies the intent, picks the right downstream agent, and runs it in-process. The full trace is written to the events store.

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
