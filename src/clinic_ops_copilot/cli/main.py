"""ClinicOps CLI entry point.

- `clinicops seed`       -- populate Postgres with synthetic FHIR data
- `clinicops chat`       -- send an intent through triage and the appropriate agent
- `clinicops dashboard`  -- open the Streamlit observability dashboard
- `clinicops eval`       -- run the golden eval harness
- `clinicops logs`       -- tail recent agent decisions from the events store
"""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.table import Table

from clinic_ops_copilot.config import settings
from clinic_ops_copilot.observability.tracing import configure_logging
from clinic_ops_copilot.storage.events import init_events_db, recent_events

app = typer.Typer(
    name="clinicops",
    help="Agentic operations layer for healthcare clinics.",
    no_args_is_help=False,
    invoke_without_command=True,
)
console = Console()


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context) -> None:
    """Start an interactive session when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        _run_repl()


def _run_repl() -> None:
    """Interactive REPL with in-session conversation memory."""
    import logging
    from pathlib import Path

    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.history import FileHistory
    from rich.panel import Panel

    from clinic_ops_copilot.agents.registry import registry
    from clinic_ops_copilot.agents.triage import build_triage_agent
    from clinic_ops_copilot.observability.tracing import new_trace_id

    # Suppress httpx transport noise — users don't need to see HTTP wire logs
    logging.getLogger("httpx").setLevel(logging.WARNING)

    configure_logging(settings.log_level)
    init_events_db()

    loaded = _setup_registry()

    triage = build_triage_agent()
    trace = new_trace_id()

    # prompt_toolkit session: persistent history across REPL sessions,
    # up-arrow recall, ctrl-r reverse search, inline autosuggest.
    history_path = Path.home() / ".clinicops_history"
    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(history_path)),
        auto_suggest=AutoSuggestFromHistory(),
    )
    # ANSI-styled prompt (prompt_toolkit doesn't use rich markup)
    prompt_text = ANSI("\x1b[1;36myou\x1b[0m \x1b[2m▶\x1b[0m ")

    console.print(
        Panel(
            "[bold cyan]ClinicOps Copilot[/bold cyan]\n"
            "[dim]Describe what you need and I'll route you to the right team.\n"
            "Type [bold]exit[/bold] or press [bold]ctrl+c[/bold] to quit.\n"
            "Up/down arrows recall history · ctrl+r reverse search[/dim]"
            + (f"\n[dim]plugins: {', '.join(loaded)}[/dim]" if loaded else ""),
            border_style="cyan",
            padding=(0, 1),
        )
    )
    console.print()

    # session_history: full conversation — passed to triage each turn so it
    # can make context-aware routing decisions (orchestrator pattern).
    # agent_histories: per-agent history — each downstream agent only sees
    # its own prior exchanges, keeping context focused.
    session_history: list[dict] = []
    agent_histories: dict[str, list[dict]] = {}

    # Stream handler: print agent text as it arrives. We write directly to
    # the underlying file so rich's markup parsing doesn't choke on partial
    # tokens and user-generated text.
    def stream_chunk(text: str) -> None:
        console.file.write(text)
        console.file.flush()

    while True:
        try:
            user_input = session.prompt(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            console.print("[dim]bye[/dim]")
            break

        # Orchestrator: triage runs every turn with full session context so it
        # can distinguish follow-ups from topic switches.
        triage_result = triage.run(user_input, trace_id=trace, prior_messages=session_history)
        if triage_result.error:
            console.print(f"[red]Triage error:[/red] {triage_result.error}")
            continue

        target = None
        for tc in triage_result.tool_calls:
            if tc.get("tool") == "route_to_agent":
                target = tc.get("output", {}).get("target")
                break

        if not target or target == "human":
            # Triage handles this directly: escalation or clarifying question
            console.print(triage_result.final_text)
            session_history.append({"role": "user", "content": user_input})
            session_history.append({"role": "assistant", "content": triage_result.final_text})
            continue

        target_reg = registry.get(target)
        if not target_reg:
            console.print(f"[yellow]No agent registered for '{target}'[/yellow]")
            continue

        agent = target_reg.factory()
        console.print(f"[dim]→ {target}[/dim]")

        agent_history = agent_histories.setdefault(target, [])
        result = agent.run(
            user_input,
            trace_id=trace,
            prior_messages=agent_history,
            on_text_chunk=stream_chunk,
        )
        console.print()  # newline after streamed output

        if result.error:
            console.print(f"[red]Error:[/red] {result.error}")
            continue

        # Update both histories
        turn = [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": result.final_text},
        ]
        session_history.extend(turn)
        agent_history.extend(turn)


def _setup_registry() -> list[str]:
    """Register built-in agents and discover plugins from ./plugins/."""
    from pathlib import Path

    from clinic_ops_copilot.agents.eligibility import build_eligibility_agent
    from clinic_ops_copilot.agents.registry import registry
    from clinic_ops_copilot.agents.scheduler import build_scheduler_agent

    registry.register(
        "scheduler",
        "Books, reschedules, and cancels patient appointments.",
        build_scheduler_agent,
    )
    registry.register(
        "eligibility",
        "Checks patient insurance coverage and prior authorization requirements.",
        build_eligibility_agent,
    )

    plugins_dir = Path.cwd() / "plugins"
    return registry.discover(plugins_dir)


@app.command()
def seed(
    patients: int = typer.Option(1000, "--patients", "-n", help="Number of synthetic patients"),
) -> None:
    """Generate synthetic FHIR data and load it into Postgres."""
    import importlib.util
    from pathlib import Path

    init_events_db()

    seed_path = Path.cwd() / "scripts" / "seed.py"
    if not seed_path.exists():
        console.print(f"[red]seed.py not found:[/red] {seed_path}")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("seed", seed_path)
    if spec is None or spec.loader is None:
        console.print("[red]Failed to load seed.py[/red]")
        sys.exit(1)
    seed_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed_module)  # type: ignore[union-attr]
    seed_module.main(num_patients=patients)


@app.command()
def chat(
    intent: str = typer.Argument(..., help="Clinical intent to process"),
) -> None:
    """Send an intent through triage and the appropriate downstream agent."""
    from clinic_ops_copilot.agents.registry import registry
    from clinic_ops_copilot.agents.triage import build_triage_agent
    from clinic_ops_copilot.observability.tracing import new_trace_id

    configure_logging(settings.log_level)
    init_events_db()

    loaded = _setup_registry()
    if loaded:
        console.print(f"[dim]plugins: {', '.join(loaded)}[/dim]")

    trace = new_trace_id()
    console.print(f"[dim]trace: {trace}[/dim]\n")

    triage = build_triage_agent()
    console.print("[cyan]→ triage[/cyan]")
    triage_result = triage.run(intent, trace_id=trace)

    if triage_result.error:
        console.print(f"[red]Triage error:[/red] {triage_result.error}")
        sys.exit(1)

    console.print(triage_result.final_text)

    # Find routing decision from triage tool calls
    target = None
    for tc in triage_result.tool_calls:
        if tc.get("tool") == "route_to_agent":
            target = tc.get("output", {}).get("target")
            break

    if not target or target == "human":
        return  # escalation or unrouted — triage handled it

    target_reg = registry.get(target)
    if not target_reg:
        console.print(f"[yellow]No agent registered for '{target}'[/yellow]")
        return

    agent = target_reg.factory()
    console.print(f"\n[cyan]→ {target}[/cyan]")
    result = agent.run(intent, trace_id=trace)
    if result.error:
        console.print(f"[red]Error:[/red] {result.error}")
        sys.exit(1)
    console.print(result.final_text)


@app.command()
def dashboard(
    port: int = typer.Option(8501, "--port", "-p"),
    host: str = typer.Option("localhost", "--host", "-h"),
) -> None:
    """Open the Streamlit observability dashboard."""
    import subprocess
    from pathlib import Path

    init_events_db()
    dashboard_file = Path(__file__).resolve().parent.parent / "observability" / "dashboard.py"
    if not dashboard_file.exists():
        console.print(f"[red]dashboard file not found:[/red] {dashboard_file}")
        sys.exit(1)

    console.print(f"[green]Starting dashboard at http://{host}:{port}[/green]")
    subprocess.run(
        [
            "streamlit",
            "run",
            str(dashboard_file),
            "--server.address",
            host,
            "--server.port",
            str(port),
        ],
        check=False,
    )


@app.command(name="eval")
def run_eval(
    suite: str = typer.Option("all", "--suite", "-s", help="Tag filter or 'all'"),
    no_persist: bool = typer.Option(
        False, "--no-persist", help="Do not write results to events store"
    ),
) -> None:
    """Run the golden eval harness against the agents."""
    from clinic_ops_copilot.eval.runner import run_suite, summarize

    results = run_suite(suite=suite, persist=not no_persist)
    summary = summarize(results)

    table = Table(title=f"Eval results - suite={suite}")
    table.add_column("case", style="cyan")
    table.add_column("mode")
    table.add_column("tags", style="dim")
    table.add_column("status")
    table.add_column("detail", overflow="fold")
    for r in results:
        if r.skipped:
            status = "[yellow]skip[/yellow]"
        elif r.passed:
            status = "[green]pass[/green]"
        else:
            status = "[red]FAIL[/red]"
        table.add_row(
            r.case_id,
            r.mode,
            ",".join(r.tags),
            status,
            r.detail,
        )
    console.print(table)
    console.print(
        f"[bold]{summary['passed']}/{summary['total']} passed[/bold] "
        f"({summary['failed']} failed, {summary['skipped']} skipped)"
    )

    sys.exit(1 if summary["failed"] > 0 else 0)


@app.command()
def logs(
    agent: str = typer.Option("all", "--agent", "-a"),
    limit: int = typer.Option(20, "--limit", "-n"),
) -> None:
    """Tail recent agent decisions from the events store."""
    init_events_db()
    rows = recent_events(agent=agent, limit=limit)
    if not rows:
        console.print("[yellow]No events recorded yet.[/yellow]")
        return

    table = Table(title=f"Recent events ({agent})")
    table.add_column("ts", style="cyan", no_wrap=True)
    table.add_column("trace", style="dim")
    table.add_column("agent", style="green")
    table.add_column("type")
    table.add_column("tool")
    table.add_column("ms", justify="right")
    table.add_column("status")
    for r in rows:
        table.add_row(
            r["timestamp"][:19],
            r["trace_id"][:12],
            r["agent"],
            r["event_type"],
            r["tool_name"] or "",
            str(r["latency_ms"] or ""),
            r["status"],
        )
    console.print(table)


@app.command()
def healthcheck() -> None:
    """Verify Postgres and the events store are reachable."""
    from clinic_ops_copilot.storage.database import healthcheck as db_check

    init_events_db()
    db_ok = db_check()
    console.print(f"Postgres: {'[green]ok[/green]' if db_ok else '[red]unreachable[/red]'}")
    console.print("Events store: [green]ok[/green]")
    console.print(
        f"LLM API key: {'[green]set[/green]' if settings.llm_api_key else '[red]missing[/red]'}"
    )
    sys.exit(0 if db_ok else 1)


if __name__ == "__main__":
    app()
