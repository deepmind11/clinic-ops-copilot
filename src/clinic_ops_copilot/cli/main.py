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
    no_args_is_help=True,
)
console = Console()


@app.command()
def seed(
    patients: int = typer.Option(1000, "--patients", "-n", help="Number of synthetic patients"),
) -> None:
    """Generate synthetic FHIR data and load it into Postgres."""
    init_events_db()
    from scripts import seed as seed_module  # type: ignore[import-not-found]

    seed_module.main(num_patients=patients)


@app.command()
def chat(
    intent: str = typer.Argument(..., help="Clinical intent to process"),
) -> None:
    """Send an intent through triage and the appropriate downstream agent."""
    from clinic_ops_copilot.agents.eligibility import build_eligibility_agent
    from clinic_ops_copilot.agents.scheduler import build_scheduler_agent
    from clinic_ops_copilot.agents.triage import build_triage_agent
    from clinic_ops_copilot.observability.tracing import new_trace_id

    configure_logging(settings.log_level)
    init_events_db()
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

    if target == "scheduler":
        agent = build_scheduler_agent()
        console.print("\n[cyan]→ scheduler[/cyan]")
    elif target == "eligibility":
        agent = build_eligibility_agent()
        console.print("\n[cyan]→ eligibility[/cyan]")
    else:
        return  # triage handled it (escalation or unrouted)

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
        f"OpenRouter API key: {'[green]set[/green]' if settings.openrouter_api_key else '[red]missing[/red]'}"
    )
    sys.exit(0 if db_ok else 1)


if __name__ == "__main__":
    app()
