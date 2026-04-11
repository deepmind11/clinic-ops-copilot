# Golden Eval Cases

This directory holds `cases.json`, the golden test suite for the eval harness.

## Case format

Each case lives in the `cases` array of `cases.json`. Cases run in one of two modes:

### Deterministic cases

Call a tool function directly with known inputs and assert on the return value. These run in CI without any API keys or database — they form the contract layer for each tool's surface.

```json
{
  "id": "elig-01",
  "tags": ["eligibility"],
  "mode": "deterministic",
  "tool": "get_payor_rules",
  "input": {"payor": "Aetna", "service_code": "D1110"},
  "expected": {"covered": true, "prior_auth_required": false}
}
```

### Agent cases

Invoke the real LLM-backed agent over its full tool surface. Requires `LLM_API_KEY` and (for Scheduler/Eligibility/Onboarding cases) a seeded Postgres. Gracefully skipped if the prerequisites aren't present, so CI stays green.

```json
{
  "id": "sched-01",
  "tags": ["scheduling"],
  "mode": "agent",
  "agent": "scheduler",
  "input": "I need to book a cleaning tomorrow at 10am for Maria Lopez.",
  "expected": {
    "tool_calls_any_of": ["lookup_patient", "find_open_slots"],
    "final_text_should_not_contain": ["error", "I cannot"]
  }
}
```

## Expectation matchers

- **Plain key** — exact equality: `"covered": true`
- **`*_in`** — value must be in a list: `"top_class_in": ["scheduling", "escalation"]`
- **`*_contains`** — string must contain the given substring (case-insensitive): `"reason_contains": "excluded"`
- **`tool_calls_any_of`** — at least one of the named tools must have been called by the agent
- **`final_text_should_not_contain`** — the agent's final text must not contain any of these phrases (case-insensitive)

## Categories covered

- **Scheduling** — booking, reschedule, cancel, provider-unavailable fallback, same-day requests
- **Eligibility** — payor rules: Aetna, Cigna, Blue Cross, Medicare, unknown payor
- **Triage classifier (deterministic)** — English, Spanish, English-Spanish code-switching mid-utterance, urgency detection, ambiguous-input fallback
- **Triage agent** — assistant delegates through `delegate_to_*` tools (or escalates) for multilingual and ambiguous inputs
- **Onboarding** — new-patient registration flow with name, phone, date of birth

## Running

```bash
uv run clinicops eval                    # all cases
uv run clinicops eval --suite eligibility # tag-filtered subset
uv run clinicops eval --no-persist       # skip writing to events store
```

Pass/fail is written to the events store's `eval_runs` table and surfaced in the dashboard under the "Eval harness" panel.
