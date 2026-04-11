# Architecture

## Design Goals

ClinicOps Copilot is designed for real-world clinic operations deployment. These goals drive every architectural decision below.

1. **Real healthcare data shapes.** FHIR R4, not toy schemas.
2. **Observability is first-class, not an add-on.** Every tool call is traced end-to-end.
3. **Single-chatbot UX.** The patient talks to one assistant; specialized workers are invisible.
4. **A CLI a customer's IT team can run.** Not a Jupyter notebook demo.
5. **Eval harness blocks promotion.** Correctness is provable, not aspirational.
6. **Extensible by design.** New workflows are added as plugin files — no core code changes required.
7. **Pragmatic dependencies.** OpenAI SDK (any OpenAI-compatible provider), Postgres, Streamlit, Faker. No exotic tools, no churning frameworks.

## Component Map

### CLI (`clinicops`)

The single entry point. With no subcommand, it drops into an interactive REPL with persistent history (up/down arrows, `ctrl+r` reverse search, autosuggest from `~/.clinicops_history`). Subcommands:

- `clinicops` — interactive session with the ClinicOps Assistant (default)
- `clinicops chat "<intent>"` — single-shot request (useful for scripting)
- `clinicops seed --patients N` — generate synthetic patients via Faker + `fhir.resources`, load into Postgres
- `clinicops dashboard` — open the Streamlit observability dashboard
- `clinicops eval` — run the golden test suite, write pass/fail to events store
- `clinicops logs --agent scheduler -n 20` — tail recent agent decisions
- `clinicops healthcheck` — verify Postgres and the events store are reachable

The CLI is built with Typer for ergonomics and tab completion. Agents are invoked directly in-process — no HTTP gateway. Streaming responses are piped to stdout as tokens arrive via the OpenAI SDK's streaming API.

### Agents: the "agents-as-tools" architecture

The patient talks to **one** user-facing agent — the **ClinicOps Assistant** (internally still named `triage` for backward-compat with events/eval cases). It owns the full conversation history and decides when to delegate specialized work to sub-agents.

Sub-agents are exposed to the master as **tools**: one `delegate_to_<name>` tool per registered sub-agent, plus `escalate_to_human`. Calling a delegate tool invokes a fresh sub-agent run internally, which runs its own tool-use loop and returns a structured result to the master. The master then weaves the result into natural conversation for the patient.

```
User input
    ↓
ClinicOps Assistant (master — sees full conversation)
    │
    ├── delegate_to_onboarding(request) ──→ Onboarding sub-agent runs its own
    │                                       tool loop, returns structured dict
    │
    ├── delegate_to_scheduler(request) ───→ Scheduler sub-agent runs its own
    │                                       tool loop, returns structured dict
    │
    ├── delegate_to_eligibility(request) ─→ Eligibility sub-agent runs its own
    │                                       tool loop, returns structured dict
    │
    └── escalate_to_human(reason, urgency)
    ↓
Master formulates the final response, streams it to the user
```

Key properties:

- **Sub-agents are stateless subroutines.** The master passes a focused, self-contained `request` string; the sub-agent doesn't need conversation memory. All conversation state lives on the master.
- **Trace propagation via ContextVar.** The master sets `current_trace_id` at the start of its run. Delegate tools read that var and pass it to the sub-agent, so every nested event lands under the same `trace_id` in the events store. The dashboard shows the whole chain as a single interaction.
- **Invisible handoff.** The master's system prompt explicitly forbids revealing internal routing ("never say 'routing to scheduler'"). From the user's perspective there is one assistant.
- **Dynamic tool surface.** The master's tool schemas are generated from the agent registry at build time. Registering a new plugin automatically adds a new `delegate_to_<name>` tool on the next restart.

#### Built-in sub-agents

**Onboarding**
- **Tools:** `lookup_patient(query)`, `register_patient(family_name, given_name, phone, birth_date?, language?)`
- **Role:** handle first-time-caller intake. Duplicate-checks by phone before INSERT. Validates date of birth (no future dates, no >130-year-old patients). Returns a new `patient_id` the patient can use immediately for booking or coverage checks.

**Scheduler**
- **Tools:** `find_open_slots(start_date, end_date, practitioner_id?, limit?)`, `book_appointment(slot_id, patient_id, service_code, description)`, `cancel_appointment(appointment_id)`, `lookup_patient(query)`
- **Role:** book, reschedule, cancel appointments. Handles double-bookings via row-level locking (`SELECT ... FOR UPDATE`) and falls back to nearest available slot on conflict.
- **Current datetime injected** into the system prompt at build time so the agent can resolve relative dates like "next Tuesday".

**Eligibility**
- **Tools:** `lookup_coverage(patient_id)`, `check_active_period(coverage_id, on_date)`, `get_payor_rules(payor, service_code)`
- **Role:** determine whether a patient's insurance covers a specific service on a specific date. Handles expired coverage, prior auth requirements, service exclusions, and surfaces a clear `next_action` when coverage fails.

### Storage Layer

Two stores, deliberately separated:

#### Postgres (Operational FHIR Database)

- Holds the synthetic clinic state: Patient, Appointment, Coverage, Claim, Practitioner, ProviderSlot.
- FHIR R4 resources stored as JSONB columns with extracted indexed columns (`family_name`, `phone`, `status`, etc.) for hot lookup paths. Mirrors how production healthcare systems hybridize FHIR JSON storage with relational indices.
- Tool surfaces query Postgres directly via psycopg. No ORM in the hot path; raw SQL for clarity and auditability.

#### SQLite (Events Store)

- Holds per-call telemetry: timestamp, trace_id, agent, event_type (`agent_start`, `llm_call`, `tool_call`, `agent_end`, etc.), tool_name, latency_ms, status, structured payload.
- Also holds eval run results (`eval_runs` table) for the dashboard trend panel.
- Why SQLite and not Postgres? Two stores so the operational layer never blocks on telemetry writes. SQLite is single-file, zero-config, and good enough for single-node observability. For multi-node deploys this would graduate to ClickHouse or DuckDB.

### Observability Dashboard (Streamlit)

A read-only view over the events store. Panels:

- **Per-agent call counts** (last 1h, last 24h, last 7d, all time)
- **p50/p95 latency** per agent from `llm_call` events
- **Tool-call error rate** per tool name
- **Recent decisions** with full trace expansion — click into a `trace_id` and see the master agent's delegate calls alongside each sub-agent's nested tool calls, all under the same trace
- **Eval harness pass/fail trend** over time

Streamlit chosen for speed of iteration. A production version would graduate to a custom React dashboard or a Grafana board over the events store.

### Eval Harness

Golden test cases stored in `evals/golden/cases.json`. Each case runs in one of two modes:

- **`deterministic`** — calls a tool function directly with known inputs and asserts on the return. Runs in CI without API keys or Postgres. Forms the contract layer for the tool surface (payor rules, classifier keyword matching, etc.).
- **`agent`** — invokes the real LLM-backed agent over its full tool surface. Requires `LLM_API_KEY` and (for Scheduler/Eligibility/Onboarding cases) a seeded Postgres. Gracefully skipped if the prerequisites aren't available, so CI stays green.

Run with `uv run clinicops eval`. Pass/fail is written to the events store and surfaced in the dashboard. CI blocks merge on regression.

## Data Flow Example

User input: *"I'm a new patient. My name is Maria Lopez, phone 555-1234, born 1990-04-15. I'd also like to book a cleaning next Tuesday."*

1. `clinicops` REPL captures the input and calls `assistant.run(input, prior_messages=session_history, on_text_chunk=print)`.
2. Master agent streams tokens of its reply (held briefly) and emits a tool call: `delegate_to_onboarding(request="Register Maria Lopez, phone 555-1234, born 1990-04-15")`.
3. Delegate tool reads `current_trace_id`, builds a fresh Onboarding sub-agent, and calls `sub_agent.run(request, trace_id=trace)`.
4. Onboarding sub-agent calls `lookup_patient("555-1234")` — no match found.
5. Onboarding sub-agent calls `register_patient(...)` → validates input, INSERTs into Postgres, returns `{success: True, patient_id: "pat-a1b2c3d4"}`.
6. Master sees the structured result, emits another tool call: `delegate_to_scheduler(request="Book cleaning for Maria Lopez (pat-a1b2c3d4) next Tuesday at 2pm")`.
7. Scheduler sub-agent calls `find_open_slots(...)` → picks a slot → calls `book_appointment(...)` → returns confirmation.
8. Master streams the final natural-language response token-by-token: *"Welcome Maria! You're registered and I've booked you a cleaning for Tuesday April 14th at 2:00 PM..."*
9. Every event — from `agent_start` through each delegate dispatch, each sub-agent `llm_call`, each `tool_call`, to `agent_end` — is written to the events store under the same `trace_id`.
10. Streamlit dashboard shows the full trace under "Recent decisions" with nested tool calls expanded.

The patient sees one seamless conversation. The dashboard sees the whole chain.

## Why Each Dependency

| Dependency | Why |
|-----------|-----|
| openai SDK | Single client, OpenAI-compatible API. Works with OpenRouter (default), OpenAI, Ollama, LM Studio, Groq, Azure OpenAI, anything compatible. Direct SDK gives full control over the streaming tool-use loop and observability instrumentation — no framework abstraction tax |
| `prompt-toolkit` | Real REPL: persistent history, ctrl+r search, autosuggest. One dependency, meaningful UX upgrade |
| Postgres | Industry standard for healthcare. JSONB makes FHIR storage clean |
| `fhir.resources` | Official Pydantic models for FHIR R4. Saves weeks of schema work |
| Faker | Synthetic patient name / phone / date generation for seed data |
| Streamlit | Fastest path to a working dashboard. Iterates in minutes |
| Typer | Best-in-class CLI ergonomics with type hints |
| Rich | Styled terminal output (panels, tables, colors) |
| SQLite (stdlib) | Zero-config telemetry store. Single-file, fast, decoupled from operational DB |
| uv | Fast modern Python package manager |

## Plugin System

ClinicOps is designed so that different clinics can add their own workflows without touching core code.

### How it works

At startup, the CLI scans the `plugins/` directory for `.py` files and registers any it finds. A registered plugin is immediately available as a new `delegate_to_<name>` tool on the master agent — no prompt edits, no routing table changes, no core code touched.

### Plugin contract

A plugin file must define three things:

```python
AGENT_NAME = "prior_auth"          # unique name; becomes delegate_to_prior_auth
AGENT_DESCRIPTION = "..."          # shown to the master; determines when it delegates here
def build_agent() -> Agent: ...    # returns a configured sub-agent instance
```

Optionally, it can define `INTENT_KEYWORDS` to contribute keywords to the deterministic `classify_intent` utility function (useful for eval cases and plugin-scoped keyword classification).

### Initialization order

```
clinicops startup
  → register_builtins(): Onboarding, Scheduler, Eligibility registered
  → plugins/ scanned: any valid .py files registered
  → build_triage_agent() called: reads registry → generates master system prompt
    + delegate_to_<name> tool surface (one per registered agent + escalate_to_human)
  → REPL loop starts; master agent owns the conversation from here
```

### Adding a new workflow

```bash
cp plugins/_prior_auth_example.py plugins/prior_auth.py
# fill in the tool implementations
uv run clinicops
> Does patient pat-00042 need prior auth for a knee replacement?
```

No changes to the master agent, no changes to the CLI. The new workflow is live immediately.

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
- **No LangChain or LlamaIndex.** We use the raw SDK to keep the codebase self-contained and the observability homegrown. The full agent loop is ~130 lines; every abstraction is local to this repo.
- **No ORM in the hot path.** SQLAlchemy adds latency and indirection. Raw SQL is clearer and auditable.
- **No HTTP gateway.** Agents are invoked directly in-process by the CLI. For multi-tenant / multi-node deployments this would graduate to a FastAPI layer, but that's out of scope for v0.1.
- **No frontend framework beyond Streamlit.** Time better spent on agent quality and observability.
- **No persistent conversation history across sessions.** The REPL keeps history in-memory for the session. Cross-session conversation memory would require a separate store — intentionally deferred.
