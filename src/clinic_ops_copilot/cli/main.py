"""ClinicOps CLI entry point.

This is the surface a Forward Deployed Engineer would actually run on a
customer laptop. Subcommands wrap the discovery, deploy, eval, and ops
workflows that ship with the platform.
"""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="clinicops",
    help="Agentic operations layer for healthcare clinics.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def seed(
    patients: int = typer.Option(1000, "--patients", "-n", help="Number of synthetic patients to generate"),
) -> None:
    """Generate synthetic patients via Synthea and load them into Postgres."""
    console.print(f"[yellow]TODO[/yellow] seed {patients} patients (not yet implemented)")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
) -> None:
    """Start the FastAPI gateway and the agents."""
    console.print(f"[yellow]TODO[/yellow] serve on {host}:{port} (not yet implemented)")


@app.command()
def dashboard(
    port: int = typer.Option(8501, "--port", "-p"),
) -> None:
    """Open the Streamlit observability dashboard."""
    console.print(f"[yellow]TODO[/yellow] dashboard on port {port} (not yet implemented)")


@app.command(name="eval")
def run_eval(
    suite: str = typer.Option("all", "--suite", "-s", help="Eval suite name (all, scheduling, eligibility, triage, multilingual)"),
) -> None:
    """Run the golden eval harness against the agents."""
    console.print(f"[yellow]TODO[/yellow] run eval suite '{suite}' (not yet implemented)")


@app.command()
def logs(
    agent: str = typer.Option("all", "--agent", "-a"),
    since: str = typer.Option("1h", "--since"),
) -> None:
    """Tail recent agent decisions from the events store."""
    console.print(f"[yellow]TODO[/yellow] tail logs for agent='{agent}' since={since} (not yet implemented)")


if __name__ == "__main__":
    app()
