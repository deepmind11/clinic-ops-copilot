"""ClinicOps CLI entry point.

The single surface a Forward Deployed Engineer uses on the ground:
- `clinicops seed`       -- populate Postgres with synthetic FHIR data
- `clinicops serve`      -- start the FastAPI gateway
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
def serve(
    host: str = typer.Option(None, "--host", "-h"),
    port: int = typer.Option(None, "--port", "-p"),
) -> None:
    """Start the FastAPI gateway and the agents."""
    import uvicorn

    configure_logging(settings.log_level)
    init_events_db()
    uvicorn.run(
        "clinic_ops_copilot.api.main:app",
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=False,
    )


@app.command()
def dashboard(
    port: int = typer.Option(8501, "--port", "-p"),
) -> None:
    """Open the Streamlit observability dashboard."""
    console.print(f"[yellow]TODO[/yellow] Streamlit dashboard on port {port} (Phase 1 backlog)")


@app.command(name="eval")
def run_eval(
    suite: str = typer.Option("all", "--suite", "-s"),
) -> None:
    """Run the golden eval harness against the agents."""
    console.print(f"[yellow]TODO[/yellow] eval suite '{suite}' (Phase 1 backlog)")


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
        f"Anthropic API key: {'[green]set[/green]' if settings.anthropic_api_key else '[red]missing[/red]'}"
    )
    sys.exit(0 if db_ok else 1)


if __name__ == "__main__":
    app()
