# Contributing to ClinicOps Copilot

Thanks for your interest — this project welcomes bug reports, feature requests, and plugins.

## Ways to Contribute

- Report a bug
- Request a feature
- Improve documentation
- Write a plugin agent (the easiest way to add a new clinical workflow)
- Add eval cases to `evals/golden/`

## Code of Conduct

Be respectful. Assume good faith. Healthcare is high-stakes; so is the tone of this community.

## Development Setup

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker (for Postgres), an API key for your chosen LLM provider.

```bash
# Fork and clone
git clone https://github.com/<your-username>/clinic-ops-copilot.git
cd clinic-ops-copilot

# Install all dependencies (including dev extras)
uv sync --all-extras

# Configure your environment
cp .env.example .env
# Edit .env — set LLM_API_KEY at minimum (see .env.example for provider options)

# Start Postgres
docker compose up -d

# Seed synthetic data (100 patients is enough for dev)
uv run clinicops seed --patients 100
```

## Running Tests

These commands mirror CI exactly — if they pass locally, they pass in CI.

```bash
# Lint
uv run ruff check .

# Format check
uv run ruff format --check .

# Type check (runs with continue-on-error in CI during v0.1)
uv run pyright src tests

# Unit tests
uv run pytest tests/unit -v

# Full test suite
uv run pytest

# Eval harness (requires Postgres + LLM_API_KEY)
uv run clinicops eval
```

> Note: Pyright may surface type errors in v0.1 that CI tolerates. Don't let that block you — fix what you can and note the rest in your PR description.

## Submitting a Pull Request

1. Create a topic branch off `main`: `git checkout -b feat/<short-description>`
2. Write tests first — see `tests/unit/test_smoke.py` for style.
3. Keep commits focused; one logical change per commit.
4. Run the full local CI pipeline (the four commands above) before pushing.
5. Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `perf:`, `ci:`.
6. Push and open a PR against `main`. Fill in the description with motivation, what changed, and a test plan.
7. Every PR must update `## [Unreleased]` in `CHANGELOG.md`.
8. CI must be green before merge.

## Plugin Development

The easiest way to contribute a new clinical workflow is a plugin — a single `.py` file dropped into `plugins/`. No changes to core code required.

ClinicOps uses an **agents-as-tools** pattern: the patient talks to one user-facing ClinicOps Assistant, which delegates specialized work to sub-agents via `delegate_to_<name>` tool calls. A plugin is a sub-agent the registry picks up at startup. When you add a plugin named `prior_auth`, the assistant automatically gains a `delegate_to_prior_auth` tool.

See [`plugins/README.md`](plugins/README.md) for the full contract. The reference implementation is [`plugins/_prior_auth_example.py`](plugins/_prior_auth_example.py) — the `_` prefix keeps it inactive; rename it to activate.

**Quick summary of the contract:**

```python
# plugins/my_workflow.py
AGENT_NAME = "my_workflow"           # becomes delegate_to_my_workflow on the assistant
AGENT_DESCRIPTION = "One sentence."  # drives routing — describe what the workflow handles

def build_agent():
    from clinic_ops_copilot.agents.base import Agent
    return Agent(name=AGENT_NAME, system_prompt=SYSTEM_PROMPT, tools=TOOLS, tool_funcs=TOOL_FUNCS)
```

**Testing a plugin locally:**

```bash
# Drop your file into plugins/ and start an interactive session
uv run clinicops
> Does patient pat-00042 need prior auth for a knee replacement?

# Or a one-shot request:
uv run clinicops chat "Does patient pat-00042 need prior auth for a knee replacement?"

# Check the tool-call trace in the dashboard
uv run clinicops dashboard
```

**Submitting a plugin via PR:** include at least one golden eval case in `evals/golden/` that exercises the new agent.

## Reporting Bugs / Requesting Features

Use the [GitHub issue templates](https://github.com/deepmind11/clinic-ops-copilot/issues/new/choose).

## License

By contributing, you agree your contributions are licensed under the MIT License (see `pyproject.toml`).
