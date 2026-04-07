"""FastAPI gateway exposing one endpoint per agent.

Each request gets a fresh trace_id that propagates through the agent's
tool calls and lands in the events store. The dashboard reads from the
same store to render per-trace timelines.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from clinic_ops_copilot.agents.scheduler import build_scheduler_agent
from clinic_ops_copilot.observability.tracing import configure_logging, new_trace_id
from clinic_ops_copilot.storage.database import healthcheck as db_healthcheck
from clinic_ops_copilot.storage.events import init_events_db

configure_logging()
init_events_db()

app = FastAPI(
    title="ClinicOps Copilot",
    description="Agentic operations layer for healthcare clinics",
    version="0.1.0",
)

# Build agents at module load so each request reuses the warm Anthropic client
_scheduler = build_scheduler_agent()


class AgentRequest(BaseModel):
    intent: str
    trace_id: str | None = None


class AgentResponse(BaseModel):
    trace_id: str
    agent: str
    final_text: str
    tool_calls: list[dict] = []
    error: str | None = None


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "version": "0.1.0",
        "database_reachable": db_healthcheck(),
    }


@app.post("/agents/scheduler", response_model=AgentResponse)
def scheduler_endpoint(req: AgentRequest) -> AgentResponse:
    trace = req.trace_id or new_trace_id()
    result = _scheduler.run(req.intent, trace_id=trace)
    return AgentResponse(
        trace_id=result.trace_id,
        agent=result.agent,
        final_text=result.final_text,
        tool_calls=result.tool_calls,
        error=result.error,
    )
