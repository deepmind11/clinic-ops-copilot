# ClinicOps Copilot

[![CI](https://github.com/deepmind11/clinic-ops-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/deepmind11/clinic-ops-copilot/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

> Multi-agent AI system for clinic operations over a FHIR R4 database, with first-class observability and a deployable CLI.

---

## What This Is

ClinicOps Copilot is a working multi-agent system for clinic operations. It operates over a synthetic FHIR R4 patient database and handles real edge cases — new-patient intake, booking conflicts, expired coverage, code-switched Spanish intents. Every tool call is traced to a Streamlit observability dashboard.

The patient always talks to a single **ClinicOps Assistant**. Behind the scenes, the assistant delegates specialized work to sub-agents (Onboarding, Scheduler, Eligibility) via `delegate_to_<name>` tool calls — an *agents-as-tools* architecture where sub-agents are invoked as stateless subroutines and the handoff is invisible to the user.

Sub-agents live in an **agent registry**. Built-ins register at startup, and new workflows are added by dropping a single `.py` file into `plugins/` — the assistant automatically picks it up as another delegate tool. A single CLI (`clinicops`) handles seeding, interactive chat, dashboard, and evals.

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
  +-------------------------------------+
  |       CLI (clinicops)               |   REPL, seed, eval, dashboard, logs
  |  streaming output · prompt history  |
  +------------------+------------------+
                     |
                     v
  +-------------------------------------+
  |       ClinicOps Assistant           |   single user-facing agent
  |          (master / triage)          |   owns conversation state
  +------------------+------------------+
                     |  delegate_to_<name>(request)  (internal tool calls)
     +---------------+---------------+
     |               |               |
     v               v               v
  +-------+      +---------+      +-----------+
  |Onboard|      |Scheduler|      |Eligibility|       each is a sub-agent
  |  ing  |      |         |      |           |       with its own tool
  +---+---+      +----+----+      +-----+-----+       loop + system prompt
      |               |                 |
      +---------------+-----------------+
                      |
                      v  (raw SQL via psycopg)
          +-----------------------+       +--------------+
          |      Postgres         |       |  SQLite      |
          |     (FHIR R4)         |       |  Events      |
          |  Patient              |       |  Store       |
          |  Appointment          |       |  per-call    |
          |  Coverage             |       |  metrics     |
          |  Practitioner         |       +------+-------+
          |  ProviderSlot · Claim |              |
          +-----------------------+              v
                                         +--------------+
                                         |  Streamlit   |
                                         | Observability|
                                         |  Dashboard   |
                                         +--------------+
```

- The **Assistant** is the only thing the patient sees. It owns the conversation, decides when to delegate, and streams its responses token-by-token.
- **Delegate calls** propagate the master's `trace_id` via a `ContextVar` so every sub-agent event lands under the same trace in the events store — the dashboard shows the whole chain as one interaction.
- **Plugins** register in the same registry and automatically become new `delegate_to_<plugin_name>` tools on the assistant.

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

On next startup the assistant automatically picks up the plugin as a new `delegate_to_prior_auth` tool and starts routing relevant requests to it. No changes to core code required.

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

The golden test suite runs in two modes per case:

- **Deterministic** — calls a tool function directly with known inputs and asserts on the return value. Runs in CI with no API keys or database.
- **Agent** — invokes the real LLM-backed agent over its tool surface. Requires `LLM_API_KEY` and a seeded Postgres; skipped gracefully if the prerequisites are missing.

The suite covers:

- **Scheduling:** booking flow, reschedule, cancel, provider-unavailable fallbacks, same-day requests
- **Eligibility:** payor rules (Aetna, Cigna, Blue Cross, Medicare, unknown payor)
- **Triage (classifier):** English, Spanish, English-Spanish code-switching mid-utterance, urgency detection
- **Triage (agent):** assistant routes through `delegate_to_*` tools
- **Onboarding:** new-patient registration flow

Run them with `uv run clinicops eval`. Pass/fail metrics are written to the events store and surfaced in the dashboard.

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
├── CHANGELOG.md               # what shipped in each release
├── CONTRIBUTING.md            # dev setup, tests, plugin guide
├── docs/
│   ├── ARCHITECTURE.md        # design decisions
│   └── QUICKSTART.md          # full walkthrough
├── plugins/                   # drop .py files here to add new workflows
│   ├── README.md              # plugin contract and how-to
│   └── _prior_auth_example.py # reference implementation (prefixed _ = inactive)
├── src/clinic_ops_copilot/
│   ├── agents/                # base, registry, triage (master), onboarding,
│   │                          # scheduler, eligibility
│   ├── tools/                 # tool surfaces for each sub-agent
│   ├── storage/               # Postgres queries, events store, database helpers
│   ├── observability/         # logging, tracing, Streamlit dashboard
│   ├── eval/                  # eval harness runner
│   └── cli/                   # clinicops CLI (REPL + subcommands)
├── tests/
│   └── unit/                  # smoke tests for agents, tools, registry, evals
├── evals/golden/cases.json    # golden test cases
├── scripts/
│   ├── init.sql               # Postgres schema
│   └── seed.py                # synthetic FHIR data generator
└── data/synthea/              # generated synthetic data (gitignored)
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the phased plan.

