# ClinicOps Copilot

> Multi-agent AI system for clinic operations over a FHIR R4 database, with first-class observability and a deployable CLI.

**License:** MIT

---

## What This Is

ClinicOps Copilot is a working multi-agent system where three Claude agents (Scheduler, Eligibility, Triage) operate over a synthetic FHIR R4 patient database, handle real edge cases (booking conflicts, expired coverage, code-switched Spanish intents), and stream every tool call to a Streamlit observability dashboard. A single CLI (`clinicops`) handles seeding, deployment, and evals. A Terraform module deploys the whole thing to AWS Lambda + RDS in one command.

## Architecture

```
                  +-------------------+
                  |  CLI (clinicops)  |   discovery, deploy, eval, seed
                  +---------+---------+
                            |
                  +---------v---------+
                  |  FastAPI Gateway  |
                  +---------+---------+
                            |
              +-------------+-------------+
              |             |             |
        +-----v----+  +-----v----+  +-----v-----+
        |Scheduler |  |Eligibility|  |  Triage  |    Claude Agent SDK
        |  Agent   |  |   Agent   |  |   Agent  |    (multi-agent)
        +-----+----+  +-----+----+  +-----+-----+
              |             |             |
              +------+------+------+------+
                     |             |
              +------v------+   +--v---------+
              |  Postgres   |   |  Events    |
              | (FHIR R4)   |   |  Store     |
              | Patient     |   | (SQLite)   |
              | Appointment |   | per-call   |
              | Coverage    |   | metrics    |
              | Claim       |   +------+-----+
              +-------------+          |
                                +------v------+
                                | Streamlit   |
                                | Observability|
                                | Dashboard   |
                                +-------------+
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design decisions.

## The Three Agents (Phase 1)

| Agent | Status | Role | Tool Calls |
|-------|--------|------|------------|
| **Scheduler** | shipped | Books, reschedules, cancels appointments. Handles double-bookings, slot conflicts, provider availability. | `find_open_slots`, `book_appointment`, `cancel_appointment`, `lookup_patient` |
| **Eligibility** | shipped | Checks insurance coverage status from FHIR Coverage resource. Flags expired plans, missing prior auth, ineligible services. | `lookup_coverage`, `check_active_period`, `get_payor_rules` |
| **Triage** | shipped | Routes new patient intents to the right downstream agent or human. Handles Spanish code-switching. | `classify_intent`, `route_to_agent`, `escalate_to_human` |

A fourth **Billing/RCM** agent is planned for Phase 2. See [ROADMAP.md](ROADMAP.md).

## Tech Stack

- **Language:** Python 3.11+
- **Agent framework:** OpenAI Python SDK pointed at OpenRouter (`anthropic/claude-sonnet-4.5` by default) with a custom tool-use loop (no LangChain, no LlamaIndex, no abstraction tax). Single provider, no provider-switching code paths.
- **Web layer:** FastAPI
- **Data layer:** PostgreSQL with FHIR R4 schema via `fhir.resources` Pydantic models
- **Synthetic data:** [Synthea](https://github.com/synthetichealth/synthea) (open-source synthetic patient generator)
- **Observability:** SQLite events store + Streamlit dashboard
- **Eval harness:** Plain Python + 20 golden test cases (booking conflicts, coverage edge cases, Spanish code-switching)
- **Infrastructure:** Terraform module for AWS Lambda + RDS
- **CI/CD:** GitHub Actions (lint, type check, tests, eval harness on every PR)
- **Packaging:** uv

## Quick Start (Local)

```bash
# Clone
git clone https://github.com/deepmind11/clinic-ops-copilot.git
cd clinic-ops-copilot

# Install
uv sync

# Configure OpenRouter (single LLM provider; OpenAI-compatible API)
export OPENROUTER_API_KEY=sk-or-v1-...
# Optional overrides:
# export OPENROUTER_MODEL=anthropic/claude-sonnet-4.5
# export OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Start Postgres + load synthetic data
docker compose up -d
clinicops seed --patients 1000

# Run the agents
clinicops serve

# Open the observability dashboard
clinicops dashboard

# Run the eval harness
clinicops eval
```

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for the full walkthrough.

## Live Demo

Phase 2 will ship a public AWS-hosted demo URL. For now, watch the 90-second Loom: *(coming with v0.1)*.

## Eval Harness

The 20 golden test cases cover:

- **Scheduling:** double-booked slots, provider unavailable, same-day requests, slot conflicts
- **Eligibility:** expired coverage, missing prior auth, ineligible service, payor rule mismatch
- **Triage:** new patient intake, urgent re-routing, escalation criteria
- **Multilingual:** Spanish intents, English-Spanish code-switching mid-utterance (a known weakness across healthcare AI products)
- **Failure modes:** tool call timeouts, malformed FHIR data, downstream API errors

Run them with `clinicops eval`. Pass/fail metrics are written to the events store and surfaced in the dashboard.

## Why FHIR?

FHIR R4 is the wire format every modern healthcare integration touches. Most LLM portfolio projects use generic SQL or made-up schemas. This one uses the standard, so the integration patterns shown here transfer directly to real EHR work (Epic, Cerner, Athenahealth, OpenEMR).

The data is synthetic, generated by [Synthea](https://github.com/synthetichealth/synthea), which is the open-source standard for synthetic patient data used by HL7, ONC, and most healthcare AI vendors during development.

## Why Observability Is First-Class

Most agent demos have no telemetry. In production, observability is the first thing customers ask about after initial deployment. This project ships a Streamlit dashboard out of the box — not a wishlist feature for v2.

The dashboard surfaces:
- Per-agent call counts
- p50/p95 latency
- Tool-call error rate
- Sample of recent decisions with full trace (prompt, tool calls, tool responses, final answer)
- Eval harness pass/fail trend

## Tradeoffs and What I Would Do With More Time

- **Multi-tenant row-level security** with Postgres RLS so multiple clinics can share infra safely
- **Real EHR integration** via [OpenEMR](https://www.open-emr.org/) FHIR API or a Mirth Connect integration channel
- **Eval harness on production traces** -- replay real anonymized customer traffic against new prompts before promotion
- **Latency-aware routing** -- fall back to a cheaper model for high-confidence intents
- **PHI redaction layer** -- Presidio or a custom NER model in front of every prompt

## Project Structure

```
clinic-ops-copilot/
├── README.md                  # this file
├── ROADMAP.md                 # phased delivery plan
├── docs/
│   ├── ARCHITECTURE.md        # design decisions
│   ├── QUICKSTART.md          # full walkthrough
│   └── EVALS.md               # eval harness details
├── src/clinic_ops_copilot/
│   ├── agents/                # Scheduler, Eligibility, Triage
│   ├── tools/                 # tool surfaces wrapping Postgres
│   ├── api/                   # FastAPI gateway
│   ├── storage/               # FHIR Pydantic models, Postgres, events store
│   ├── observability/         # logging, dashboard, metrics
│   └── cli/                   # clinicops CLI
├── tests/
│   ├── unit/
│   ├── integration/
│   └── evals/                 # 20 golden test cases
├── evals/golden/              # JSON test cases
├── infra/terraform/           # AWS Lambda + RDS module
├── scripts/                   # migration, discovery, seed
└── data/synthea/              # generated synthetic data (gitignored)
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the phased plan. v0.1 ships Phase 1; Phase 2 adds the AWS deploy and the fourth Billing/RCM agent.

