# Architecture

## Design Goals

ClinicOps Copilot is designed for real-world clinic operations deployment. These goals drive every architectural decision below.

1. **Real healthcare data shapes.** FHIR R4, not toy schemas.
2. **Observability is first-class, not an add-on.** Every tool call is traced.
3. **A CLI a customer's IT team can run.** Not a Jupyter notebook demo.
4. **Eval harness blocks promotion.** Correctness is provable, not aspirational.
5. **Extensible by design.** New workflows are added as plugin files — no core code changes required.
6. **Pragmatic dependencies.** OpenAI SDK (pointed at OpenRouter), Postgres, Streamlit, Faker. No exotic tools, no churning frameworks.

## Component Map

### CLI (`clinicops`)

The single entry point for managing the system. Subcommands:

- `clinicops seed --patients N` -- generate synthetic patients via Synthea, load into Postgres
- `clinicops chat "<intent>"` -- run an intent through triage and the appropriate downstream agent
- `clinicops dashboard` -- open the Streamlit observability dashboard
- `clinicops eval` -- run the 20 golden test cases, write pass/fail to events store
- `clinicops logs --agent scheduler --since 1h` -- tail recent agent decisions

The CLI is built with Typer for ergonomics and tab completion. Agents are invoked directly in-process — no HTTP layer.

### Agents (OpenAI SDK pointed at OpenRouter, custom tool-use loop)

Three agents in v0.1, each with its own prompt, tool surface, and structured output schema:

#### Scheduler

- **Tools:** `find_open_slots(provider_id, date_range)`, `book_appointment(patient_id, slot_id, service_code)`, `cancel_appointment(appointment_id)`, `lookup_patient(query)`
- **Edge cases handled:** double-booked slots, provider unavailable, same-day requests, conflict resolution
- **Output schema:** `{ "action": "booked|conflict|escalated", "appointment_id": "...", "rationale": "..." }`

#### Eligibility

- **Tools:** `lookup_coverage(patient_id)`, `check_active_period(coverage_id, date)`, `get_payor_rules(payor_id, service_code)`
- **Edge cases handled:** expired coverage, missing prior auth, ineligible service, payor rule mismatch
- **Output schema:** `{ "eligible": true|false, "coverage_id": "...", "reason": "...", "next_action": "..." }`

#### Triage

- **Tools:** `classify_intent(text)`, `route_to_agent(intent_class)`, `escalate_to_human(reason)`
- **Edge cases handled:** Spanish intents, English-Spanish code-switching mid-utterance, urgent vs routine routing, escalation criteria
- **Output schema:** `{ "intent_class": "scheduling|eligibility|billing|escalation", "language": "en|es|mixed", "routed_to": "..." }`

The Triage agent's multilingual handling addresses a known weakness across healthcare AI products and is exercised by the eval harness.

Triage's system prompt and `route_to_agent` tool schema are generated dynamically at startup from the agent registry. When a new plugin is registered, Triage automatically knows about it — no prompt edits required.

### Storage Layer

Two stores, deliberately separated:

#### Postgres (Operational FHIR Database)

- Holds the synthetic clinic state: Patient, Appointment, Coverage, Claim, Practitioner.
- FHIR R4 resources serialized via `fhir.resources` Pydantic models, then stored as JSONB columns with extracted indexed columns for hot lookup paths.
- Tool surfaces query Postgres directly. No ORM in the hot path; raw SQL for clarity and performance.

#### SQLite (Events Store)

- Holds per-call telemetry: timestamp, trace_id, agent, tool_name, latency_ms, success/error, full prompt, full response.
- Why SQLite and not Postgres? Two stores so the operational layer never blocks on telemetry writes. SQLite is single-file, zero-config, and good enough for single-node observability. For multi-node deploys this would graduate to ClickHouse or DuckDB.

### Observability Dashboard (Streamlit)

A read-only view over the events store. Panels:

- **Per-agent call counts** (last hour, last 24h, last 7d)
- **p50/p95 latency** per agent
- **Tool-call error rate** per tool
- **Recent decisions** with full trace expansion
- **Eval harness pass/fail trend** over time

Streamlit chosen for speed of iteration. A production version would graduate to a custom React dashboard or a Grafana board over the events store.

### Eval Harness

20 golden test cases stored as JSON in `evals/golden/`. Each case is a tuple of:

- Input intent
- Expected agent
- Expected tool call sequence (or a relaxed match)
- Expected output schema field values
- Tags (`scheduling`, `eligibility`, `triage`, `multilingual`, `failure_mode`)

Run with `clinicops eval`. Pass/fail is written to the events store and surfaced in the dashboard. CI blocks merge on regression.

## Data Flow Example

User intent: *"tengo dolor de muelas y necesito ver al dentista hoy"*

1. `clinicops chat "<intent>"` starts a trace and runs the Triage agent in-process
2. Triage agent calls `classify_intent` tool, gets back `{"class": "scheduling", "urgency": "high", "language": "es"}`
3. Triage agent calls `route_to_agent("scheduling")`, returns `{"target": "scheduler"}`
4. CLI reads the routing decision and runs the Scheduler agent in-process with the same trace_id
5. Scheduler agent calls `find_open_slots(provider_id=any_dentist, date_range=today)`
6. Scheduler agent calls `book_appointment(...)` for the first available slot
7. Final response printed to the terminal
8. Every tool call logged to the events store with trace_id linking the chain
9. Streamlit dashboard shows the full trace under "Recent decisions"

## Why Each Dependency

| Dependency | Why |
|-----------|-----|
| openai SDK (pointed at OpenRouter) | Single LLM provider, OpenAI-compatible API, model-agnostic. Default model is `anthropic/claude-sonnet-4.5`. Direct SDK gives full control over observability instrumentation, no framework abstraction tax |
| Postgres | Industry standard for healthcare. JSONB makes FHIR storage clean |
| `fhir.resources` | Official Pydantic models for FHIR R4. Saves weeks of schema work |
| Synthea | Industry-standard synthetic patient generator. Used by HL7 and ONC |
| Streamlit | Fastest path to a working dashboard. Iterates in minutes |
| Typer | Best-in-class CLI ergonomics with type hints |
| SQLite | Zero-config telemetry store. Single-file, fast, decoupled from operational DB |
| uv | Fast modern Python package manager. Standard in 2026 AI engineering |

## Plugin System

ClinicOps is designed so that different clinics can add their own workflows without touching core code.

### How it works

At startup, the CLI scans the `plugins/` directory for `.py` files and registers any it finds. A registered plugin becomes a first-class agent: Triage knows about it, can route to it, and the `clinicops chat` command can invoke it.

### Plugin contract

A plugin file must define three things:

```python
AGENT_NAME = "prior_auth"          # unique routing key
AGENT_DESCRIPTION = "..."          # shown to Triage; determines when it routes here
def build_agent() -> Agent: ...    # returns a configured Agent instance
```

Optionally, it can define `INTENT_KEYWORDS` to improve the keyword classifier's confidence when routing to the new agent.

### Initialization order

```
clinicops chat starts
  → registry populated: built-ins (scheduler, eligibility) registered
  → plugins/ scanned: any valid .py files registered
  → build_triage_agent() called: reads registry → generates system prompt + route enum
  → chat loop runs
```

### Adding a new workflow

```bash
cp plugins/_prior_auth_example.py plugins/prior_auth.py
# fill in the tool implementations
clinicops chat "Does patient 123 need prior auth for a knee replacement?"
```

No changes to Triage, no changes to the CLI. The new agent is live immediately.

### Plugin file naming

Files starting with `_` are skipped by the registry (examples, drafts). Rename without the leading `_` to activate.

### Common workflow categories

| Category | What it handles |
|---|---|
| Prior Authorization | Pre-approval checks, auth status |
| Referral Management | Specialist referrals, referral status |
| Lab Results | Abnormal flagging, provider notification |
| Medication Management | Refill requests, drug prior auth |
| Billing / RCM | Claim status, denial classification |
| Patient Outreach | Reminders, follow-up communication |
| Discharge Planning | Post-care coordination |

See `plugins/README.md` for the full contract and a reference implementation.

## What Is Deliberately Not Here

- **No vector database.** Agents use structured tool calls, not RAG. Healthcare ops decisions need to be auditable, and vector retrieval is opaque.
- **No LangChain or LlamaIndex.** We use the raw SDK to keep the codebase self-contained and the observability homegrown. LangChain or LangGraph with Langfuse would be equally valid and more familiar to teams already in that ecosystem.
- **No ORM in the hot path.** SQLAlchemy adds latency and indirection. Raw SQL is clearer.
- **No frontend framework beyond Streamlit.** Time better spent on agent quality and observability.
