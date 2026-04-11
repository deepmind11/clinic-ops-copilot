# ClinicOps Copilot

[![CI](https://github.com/deepmind11/clinic-ops-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/deepmind11/clinic-ops-copilot/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

> Multi-agent AI system for clinic operations over a FHIR R4 database, with first-class observability and a deployable CLI.

---

## What This Is

ClinicOps Copilot is a working multi-agent system for clinic operations. Three built-in agents (Scheduler, Eligibility, Triage) operate over a synthetic FHIR R4 patient database and handle real edge cases — booking conflicts, expired coverage, code-switched Spanish intents. Every tool call is traced to a Streamlit observability dashboard.

The system is built around an **agent registry**: a central directory of available workflows that Triage reads at startup to decide where to route each patient intent. Built-in agents are registered automatically. New workflows are added by dropping a single `.py` file into `plugins/` — no core code changes required. A single CLI (`clinicops`) handles seeding, chat, and evals.

## Quick Start

```bash
# Clone
git clone https://github.com/deepmind11/clinic-ops-copilot.git
cd clinic-ops-copilot

# Install
uv sync --all-extras

# Configure — copy the example and fill in your API key
cp .env.example .env
# Edit .env and set LLM_API_KEY (see .env.example for provider options)

# Start Postgres + load synthetic data
docker compose up -d
uv run clinicops seed --patients 1000

# Start an interactive session
uv run clinicops

# Open the observability dashboard
uv run clinicops dashboard

# Run the eval harness
uv run clinicops eval
```

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for the full walkthrough.

## Architecture

```
                  +-------------------+
                  |  CLI (clinicops)  |   chat, seed, eval, logs
                  +---------+---------+
                            |
                  +---------v---------+
                  |   Triage Agent    |   classifies intent, routes
                  +---------+---------+
                            |
              +-------------+-------------+
              |                           |
        +-----v----+               +-----v-----+
        |Scheduler |               |Eligibility|    OpenAI SDK
        |  Agent   |               |   Agent   |    (in-process)
        +-----+----+               +-----+-----+
              |                         |
              +------------+------------+
                           |
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

## Built-in Agents

The patient always talks to a single **ClinicOps Assistant** (the master). Behind the scenes, the master delegates to specialized sub-agents via `delegate_to_<name>` tools — the patient never sees the handoff.

| Sub-agent | Role | Tool Surface |
|-----------|------|--------------|
| **Onboarding** | Registers new patients into the FHIR database. Duplicate-checks by phone before insert. | `lookup_patient`, `register_patient` |
| **Scheduler** | Books, reschedules, and cancels appointments. Handles double-bookings, slot conflicts, provider availability. | `find_open_slots`, `book_appointment`, `cancel_appointment`, `lookup_patient` |
| **Eligibility** | Checks insurance coverage from the FHIR Coverage resource. Flags expired plans, missing prior auth, ineligible services. | `lookup_coverage`, `check_active_period`, `get_payor_rules` |

A **Billing/RCM** sub-agent is planned for Phase 2. See [ROADMAP.md](ROADMAP.md).

## Extending ClinicOps

Every clinic is different. Add your own workflow by dropping a single `.py` file into `plugins/`:

```python
# plugins/prior_auth.py
AGENT_NAME = "prior_auth"
AGENT_DESCRIPTION = "Checks prior authorization requirements and status."

def build_agent():
    from clinic_ops_copilot.agents.base import Agent
    return Agent(name=AGENT_NAME, system_prompt=SYSTEM_PROMPT, tools=TOOLS, tool_funcs=TOOL_FUNCS)
```

On next startup, Triage automatically discovers the new agent and routes to it when relevant. No changes to core code required.

See [`plugins/README.md`](plugins/README.md) for the full contract and a reference implementation (`plugins/_prior_auth_example.py`).

## Tech Stack

- **Language:** Python 3.11+
- **Agent framework:** OpenAI Python SDK with a custom tool-use loop (no LangChain, no LlamaIndex, no abstraction tax). Works with any OpenAI-compatible provider — OpenRouter (default, `anthropic/claude-sonnet-4.5`), OpenAI, or Ollama locally. Configure via `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`.
- **Data layer:** PostgreSQL with FHIR R4 schema via `fhir.resources` Pydantic models
- **Synthetic data:** [Synthea](https://github.com/synthetichealth/synthea) (open-source synthetic patient generator)
- **Observability:** SQLite events store + Streamlit dashboard
- **Eval harness:** Plain Python + 20 golden test cases (booking conflicts, coverage edge cases, Spanish code-switching)
- **CI/CD:** GitHub Actions (lint, type check, tests, eval harness on every PR)
- **Packaging:** uv

## Eval Harness

The 20 golden test cases cover:

- **Scheduling:** double-booked slots, provider unavailable, same-day requests, slot conflicts
- **Eligibility:** expired coverage, missing prior auth, ineligible service, payor rule mismatch
- **Triage:** new patient intake, urgent re-routing, escalation criteria
- **Multilingual:** Spanish intents, English-Spanish code-switching mid-utterance (a known weakness across healthcare AI products)
- **Failure modes:** tool call timeouts, malformed FHIR data, downstream API errors

Run them with `clinicops eval`. Pass/fail metrics are written to the events store and surfaced in the dashboard.

## Why FHIR?

FHIR R4 is the wire format every modern healthcare integration touches. Most LLM demo projects use generic SQL or made-up schemas. This one uses the standard, so the integration patterns shown here transfer directly to real EHR work (Epic, Cerner, Athenahealth, OpenEMR).

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
├── plugins/                   # drop .py files here to add new workflows
│   ├── README.md              # plugin contract and how-to
│   └── _prior_auth_example.py # reference implementation (prefixed _ = inactive)
├── src/clinic_ops_copilot/
│   ├── agents/                # Scheduler, Eligibility, Triage + registry
│   ├── tools/                 # tool surfaces wrapping Postgres
│   ├── storage/               # FHIR Pydantic models, Postgres, events store
│   ├── observability/         # logging, dashboard, metrics
│   └── cli/                   # clinicops CLI
├── tests/
│   ├── unit/
│   ├── integration/
│   └── evals/                 # 20 golden test cases
├── evals/golden/              # JSON test cases
├── scripts/                   # migration, discovery, seed
└── data/synthea/              # generated synthetic data (gitignored)
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the phased plan.

