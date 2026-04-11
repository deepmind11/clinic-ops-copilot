---
name: Bug report
about: Report something that is not working as expected
title: '[Bug] '
labels: bug
assignees: ''
---

## Describe the bug

A clear summary of what went wrong.

## To Reproduce

1. Run `uv run clinicops ...`
2. ...
3. See error

## Expected behavior

What you expected to happen.

## Actual behavior

What actually happened. Paste error output in a code block:

```
error output here
```

## Environment

- OS:
- Python version (`python --version`):
- uv version (`uv --version`):
- LLM provider (OpenRouter / OpenAI / Ollama / other):
- LLM model (`LLM_MODEL` value):
- Docker / Postgres version:

## Which agent is affected?

- [ ] ClinicOps Assistant (master / triage)
- [ ] Onboarding
- [ ] Scheduler
- [ ] Eligibility
- [ ] Plugin (specify name):
- [ ] CLI / REPL
- [ ] Dashboard
- [ ] Eval harness

## Logs / traces

<details>
<summary>Expand logs</summary>

```
paste logs here — use `uv run clinicops logs` or the dashboard for agent traces
```

</details>

## Additional context

Any other context about the problem.
