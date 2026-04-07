# Architecture

## Design Goals

ClinicOps Copilot is designed to be the artifact a Forward Deployed Engineer would actually deploy on day one of a customer engagement. That goal drives every architectural decision below.

1. **Real healthcare data shapes.** FHIR R4, not toy schemas.
2. **Observability is first-class, not an add-on.** Every tool call is traced.
3. **A CLI a customer's IT team can run.** Not a Jupyter notebook demo.
4. **Eval harness blocks promotion.** Correctness is provable, not aspirational.
5. **Infrastructure as code.** Terraform module ships with v0.2.
6. **Pragmatic dependencies.** Synthea, Claude Agent SDK, Postgres, Streamlit. No exotic tools.

## Component Map

### CLI (`clinicops`)

The single entry point a customer-facing engineer uses on the ground. Subcommands:

- `clinicops seed --patients N` — generate synthetic patients via Synthea, load into Postgres
- `clinicops serve` — start the FastAPI gateway and the agents
- `clinicops dashboard` — open the Streamlit observability dashboard
- `clinicops eval` — run the 20 golden test cases, write pass/fail to events store
- `clinicops logs --agent scheduler --since 1h` — tail recent agent decisions

The CLI is built with Typer for ergonomics and tab completion.

### FastAPI Gateway

A thin HTTP layer in front of the agents. One POST endpoint per agent:

- `POST /agents/scheduler` — `{ "intent": "book a cleaning next Tuesday at 2pm" }`
- `POST /agents/eligibility` — `{ "patient_id": "...", "service_code": "D1110" }`
- `POST /agents/triage` — `{ "intent": "tengo dolor de muelas y necesito ver al dentista hoy" }`

Each request is assigned a `trace_id` that propagates through every tool call and lands in the events store.

### Agents (Claude Agent SDK)

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

1. POST to `/agents/triage` with the Spanish intent
2. Triage agent calls `classify_intent` tool, gets back `{"class": "scheduling", "urgency": "high", "language": "es"}`
3. Triage agent calls `route_to_agent("scheduling")`, returns routing decision
4. FastAPI gateway forwards the original intent to `/agents/scheduler`
5. Scheduler agent calls `find_open_slots(provider_id=any_dentist, date_range=today)`
6. Scheduler agent calls `book_appointment(...)` for the first available slot
7. Final response returned to user with appointment confirmation
8. Every tool call logged to the events store with trace_id linking the chain
9. Streamlit dashboard shows the full trace under "Recent decisions"

## Why Each Dependency

| Dependency | Why |
|-----------|-----|
| Claude Agent SDK | Anthropic official multi-agent framework. Signals current tooling, not legacy LangChain |
| FastAPI | Async-first, type-safe, Pydantic-native, ubiquitous in modern Python |
| Postgres | Industry standard for healthcare. JSONB makes FHIR storage clean |
| `fhir.resources` | Official Pydantic models for FHIR R4. Saves weeks of schema work |
| Synthea | Industry-standard synthetic patient generator. Used by HL7 and ONC |
| Streamlit | Fastest path to a working dashboard. Iterates in minutes |
| Typer | Best-in-class CLI ergonomics with type hints |
| SQLite | Zero-config telemetry store. Single-file, fast, decoupled from operational DB |
| Terraform | Industry standard for IaC. AWS Lambda + RDS module is portable |
| uv | Fast modern Python package manager. Standard in 2026 AI engineering |

## What Is Deliberately Not Here

- **No vector database.** Agents use structured tool calls, not RAG. Healthcare ops decisions need to be auditable, and vector retrieval is opaque.
- **No LangChain or LlamaIndex.** Claude Agent SDK is the right level of abstraction for this use case.
- **No ORM in the hot path.** SQLAlchemy adds latency and indirection. Raw SQL is clearer.
- **No frontend framework beyond Streamlit.** Time better spent on agent quality and observability.
- **No Kubernetes.** Lambda + RDS is the right granularity for a single-tenant clinic deployment in v0.2.
