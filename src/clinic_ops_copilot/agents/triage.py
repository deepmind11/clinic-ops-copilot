"""Master agent: the single user-facing assistant for ClinicOps Copilot.

This is the only agent the patient ever talks to. It owns the full conversation
and delegates specialized work to sub-agents via `delegate_to_*` tools. Each
delegate tool is built dynamically from the agent registry at build time, so
registered plugins automatically become available workflows without any core
code changes.

From the patient's point of view there is one assistant. Behind the scenes,
the master makes focused, stateless calls into specialized sub-agents and
weaves their responses back into natural conversation. Sub-agent handoffs are
invisible — the user never sees "routing to scheduler".

The filename and ``build_triage_agent`` symbol are retained for backward
compatibility with eval cases, tests, and the events store.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from clinic_ops_copilot.agents.base import Agent, current_trace_id

# ---------------------------------------------------------------------------
# System prompt — {delegate_list} and {current_datetime} are filled at build
# ---------------------------------------------------------------------------

MASTER_SYSTEM_PROMPT_TEMPLATE = """You are the ClinicOps Assistant, an AI helping patients at a healthcare clinic.

You are the only person the patient talks to. Behind the scenes you have specialized sub-agents you can delegate work to, but the patient does NOT know about them and must not see internal routing. Respond as if you personally handled everything.

Current date and time: {current_datetime}

You support English, Spanish, and code-switched (English + Spanish) utterances. Many of our patients are bilingual and routinely switch languages mid-sentence. Treat code-switched messages as normal, not as errors. Reply in the dominant language of the patient's message.

DELEGATE TOOLS — use these to do specialized work:
{delegate_list}

You also have:
- `escalate_to_human(reason, urgency)` — escalate to a human at the front desk. Use for emergencies (severe pain, bleeding, chest pain, can't breathe / dolor severo, sangrado, dolor de pecho, no puedo respirar) or anything outside the scope of available delegate tools.

OPERATING RULES:
1. Talk to the patient naturally. Ask clarifying questions when you need more information (name, phone, date, service type, etc.) before delegating.
2. When the patient's request clearly matches one of the delegate tools, call that tool with a FOCUSED, SELF-CONTAINED request. Include all relevant context from the conversation (patient name, phone, dates, service codes) so the sub-agent has what it needs to succeed without asking follow-up questions you could have handled yourself.
3. The delegate tool returns a structured response. Summarize it in natural language for the patient — do NOT paste raw JSON and do NOT mention "the scheduler" or "the eligibility agent".
4. If the delegate tool returns an error or says more information is needed, ask the patient for what's missing and delegate again with the combined context.
5. For emergencies, call `escalate_to_human` with `urgency="emergency"`. Never try to book an appointment during an emergency.
6. If the patient's intent does not match any delegate tool, call `escalate_to_human` with a clear reason so the front desk can assist.
7. Be concise. Short replies. No internal jargon. No "based on your request" filler.

Never reveal internal routing decisions. Never say "routing to scheduler", "the scheduler agent says", "I am delegating this to...", or "transferring your call". Just respond as the ClinicOps Assistant.
"""


# ---------------------------------------------------------------------------
# Delegate tool factory — builds one delegate_to_<agent> tool per registered agent
# ---------------------------------------------------------------------------


def _make_delegate_tool(
    agent_name: str,
    factory: Callable[[], Agent],
) -> Callable[..., dict[str, Any]]:
    """Build a delegate tool that invokes a sub-agent as a stateless subroutine.

    The sub-agent receives a focused ``request`` from the master and returns a
    structured response the master can reason about. The current trace_id is
    propagated via the ``current_trace_id`` context variable so sub-agent events
    end up under the same trace in the events store.
    """

    def delegate(request: str) -> dict[str, Any]:
        trace = current_trace_id.get()
        sub_agent = factory()
        result = sub_agent.run(request, trace_id=trace)
        return {
            "agent": agent_name,
            "response": result.final_text,
            "tool_calls_made": [tc["tool"] for tc in result.tool_calls],
            "error": result.error,
        }

    return delegate


def _escalate_to_human(reason: str, urgency: str = "normal") -> dict[str, Any]:
    """Record an escalation to the front desk."""
    if urgency not in ("normal", "high", "emergency"):
        urgency = "normal"
    return {
        "escalated": True,
        "destination": "front_desk",
        "urgency": urgency,
        "reason": reason,
    }


def _build_delegate_tool_surface(
    registry_all: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Callable[..., dict[str, Any]]]]:
    """Build the master agent's tool surface from the registry.

    Returns (tool_schemas, tool_dispatch_table). One ``delegate_to_<name>`` tool
    per registered agent plus a single ``escalate_to_human`` tool.
    """
    tools: list[dict[str, Any]] = []
    tool_funcs: dict[str, Callable[..., dict[str, Any]]] = {}

    for name, reg in registry_all.items():
        tool_name = f"delegate_to_{name}"
        tools.append(
            {
                "name": tool_name,
                "description": (
                    f"{reg.description} "
                    f"Call this tool when the patient's request matches this workflow. "
                    f"Pass a focused, self-contained request including all relevant "
                    f"context from the conversation so the sub-agent can succeed "
                    f"without asking follow-up questions."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": (
                                f"A focused request for the {name} workflow. "
                                f"Include patient name, phone, dates, service codes, "
                                f"and anything else gathered from the conversation."
                            ),
                        }
                    },
                    "required": ["request"],
                },
            }
        )
        tool_funcs[tool_name] = _make_delegate_tool(name, reg.factory)

    # Always include escalate_to_human
    tools.append(
        {
            "name": "escalate_to_human",
            "description": (
                "Escalate to a human at the front desk. Use for emergencies, "
                "anything outside the available delegate tools, or when you cannot help."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "One-sentence reason for escalation",
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["normal", "high", "emergency"],
                        "description": "Urgency level",
                    },
                },
                "required": ["reason"],
            },
        }
    )
    tool_funcs["escalate_to_human"] = _escalate_to_human

    return tools, tool_funcs


def build_triage_agent() -> Agent:
    """Build the master agent. Name kept for backward compatibility."""
    from datetime import datetime

    from clinic_ops_copilot.agents.registry import registry

    # Dynamic delegate tools from registry (built-ins + plugins)
    tools, tool_funcs = _build_delegate_tool_surface(registry.all())

    # Human-readable delegate list for the system prompt
    entries = registry.all()
    if entries:
        delegate_list = "\n".join(
            f"  - delegate_to_{name}: {reg.description}" for name, reg in entries.items()
        )
    else:
        delegate_list = "  (none registered — escalate all requests to human)"

    system_prompt = MASTER_SYSTEM_PROMPT_TEMPLATE.format(
        current_datetime=datetime.now().strftime("%A, %B %d, %Y at %I:%M %p"),
        delegate_list=delegate_list,
    )

    return Agent(
        name="triage",
        system_prompt=system_prompt,
        tools=tools,
        tool_funcs=tool_funcs,
    )
