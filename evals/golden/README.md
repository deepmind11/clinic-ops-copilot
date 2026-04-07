# Golden Eval Cases

This directory holds the 20 golden test cases for the eval harness. Each case is a JSON file with the following shape:

```json
{
  "id": "scheduling-001",
  "tags": ["scheduling", "double_booking"],
  "input": {
    "agent": "scheduler",
    "intent": "Book a cleaning next Tuesday at 2pm with Dr. Smith"
  },
  "expected": {
    "agent_called": "scheduler",
    "tools_called": ["find_open_slots", "book_appointment"],
    "output_schema": {
      "action": "booked|conflict|escalated"
    },
    "must_contain_in_rationale": ["Tuesday", "2pm"]
  }
}
```

Categories covered (Phase 1):

- **Scheduling (5 cases):** double-booked slots, provider unavailable, same-day requests, slot conflicts, recurring appointments
- **Eligibility (5 cases):** expired coverage, missing prior auth, ineligible service, payor rule mismatch, secondary insurance
- **Triage (3 cases):** new patient intake, urgent re-routing, escalation criteria
- **Multilingual (4 cases):** Spanish-only intent, English-Spanish code-switching mid-utterance, formal vs informal Spanish, regional Spanish variation
- **Failure modes (3 cases):** tool call timeout, malformed FHIR data, downstream API error

Run with `clinicops eval`. Pass/fail is written to the events store and surfaced in the dashboard.
