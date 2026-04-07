# ClinicOps Copilot

> An agentic operations layer for a synthetic clinic. Multi-agent AI system over a FHIR R4 database, with first-class observability and a CLI an FDE could run on a customer laptop.

**Status:** Active build (v0.1 in progress, started 2026-04-07).
**Author:** [Harshit Ghosh](https://github.com/deepmind11)
**License:** MIT

---

## What This Is

ClinicOps Copilot simulates the reality a Forward Deployed Engineer walks into at modern healthcare AI startups: a customer with multiple legacy systems (EHR, scheduling, billing, coverage), a non-technical operations team, and a need for AI agents that handle real workflows under real constraints.

It is a working multi-agent system where three Claude agents (Scheduler, Eligibility, Triage) operate over a synthetic FHIR R4 patient database, handle real edge cases (booking conflicts, expired coverage, code-switched Spanish intents), and stream every tool call to a Streamlit observability dashboard. A single CLI (`clinicops`) handles seeding, deployment, and evals. A Terraform module deploys the whole thing to AWS Lambda + RDS in one command.

This is not a research project. It is the day-one artifact a customer-facing engineer brings into a healthcare deployment.

## Why This Project Exists

I am a bioinformatician at a CAP/CLIA oncology diagnostics lab who already ships production integration code against clinical systems (LIMS, BI databases, AWS Lambda). I am targeting Forward Deployed Engineer roles at companies building AI workers for healthcare clinics. The existing portfolio of "LangChain demo" projects on GitHub does not show what an FDE actually has to do on day one of a customer engagement: integrate with messy real-world systems, instrument everything, ship a CLI a customer's IT team can run, and prove correctness with an eval harness.

This project exists to show that work, end to end, on real healthcare data shapes.

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

| Agent | Role | Tool Calls |
|-------|------|------------|
| **Scheduler** | Books, reschedules, cancels appointments. Handles double-bookings, slot conflicts, provider availability. | `find_open_slots`, `book_appointment`, `cancel_appointment`, `lookup_patient` |
| **Eligibility** | Checks insurance coverage status from FHIR Coverage resource. Flags expired plans, missing prior auth, ineligible services. | `lookup_coverage`, `check_active_period`, `get_payor_rules` |
| **Triage** | Routes new patient intents to the right downstream agent or human. Handles Spanish code-switching. | `classify_intent`, `route_to_agent`, `escalate_to_human` |

A fourth **Billing/RCM** agent is planned for Phase 2. See [ROADMAP.md](ROADMAP.md).

## Tech Stack

- **Language:** Python 3.11+
- **Agent framework:** Claude Agent SDK (Anthropic official multi-agent SDK)
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

Most agent demos have no telemetry. In production, observability is the first thing customers ask about on day two of any deployment. This project ships a Streamlit dashboard out of the box because that is what an FDE actually needs in the field, not a wishlist feature for v2.

The dashboard surfaces:
- Per-agent call counts
- p50/p95 latency
- Tool-call error rate
- Sample of recent decisions with full trace (prompt, tool calls, tool responses, final answer)
- Eval harness pass/fail trend

## What I Would Ship in Week One on a Real Customer

This project is structured to mirror the FDE week-one playbook:

1. **Discovery scripts** (`scripts/discovery/`) — query the customer's existing systems for data shape and volume
2. **Migration pipeline** (`scripts/migrate.py`) — load legacy data into the platform
3. **Agent configuration** (`src/clinic_ops_copilot/agents/`) — tune prompts and tool surfaces per customer
4. **Observability baseline** (`src/clinic_ops_copilot/observability/`) — instrument every tool call from day one
5. **Eval harness** (`evals/`) — golden tests that block deploy if accuracy regresses

That is the FDE mindset on display in code.

## Tradeoffs and What I Would Do With More Time

- **Multi-tenant row-level security** with Postgres RLS so multiple clinics can share infra safely
- **Real EHR integration** via [OpenEMR](https://www.open-emr.org/) FHIR API or a Mirth Connect integration channel
- **Eval harness on production traces** — replay real anonymized customer traffic against new prompts before promotion
- **Latency-aware routing** — fall back to a cheaper model for high-confidence intents
- **PHI redaction layer** — Presidio or a custom NER model in front of every prompt

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

## About the Author

I am Harshit Ghosh, a bioinformatics engineer with production experience shipping integration code against clinical systems in a CAP/CLIA regulated environment. I am currently targeting Forward Deployed Engineer roles at healthcare AI startups. If you are hiring for one of those roles, my contact info is on [LinkedIn](https://linkedin.com/in/harshit-ghosh) and [GitHub](https://github.com/deepmind11).
