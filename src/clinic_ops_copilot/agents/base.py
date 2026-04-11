"""Shared agent runner built on the OpenAI SDK pointed at OpenRouter.

We deliberately use the openai Python SDK directly (against OpenRouter's
OpenAI-compatible /v1 endpoint) rather than a higher-level agent framework.
The SDK's tool-use loop is stable, well-documented, and gives us full
control over observability instrumentation. Each agent supplies a system
prompt, a tool schema list, and a tool dispatch table; the runner handles
the rest.

Tool schemas are authored in the Anthropic shape (``name``, ``description``,
``input_schema``) because that is the most compact format and the one the
agents are tested against. ``_to_openai_tools`` converts to the OpenAI
``functions`` shape at the boundary so the rest of the codebase stays
provider-agnostic.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from clinic_ops_copilot.config import settings
from clinic_ops_copilot.observability.tracing import get_logger, new_trace_id
from clinic_ops_copilot.storage.events import record_event

log = get_logger(__name__)


@dataclass
class AgentResult:
    """Final result of an agent run."""

    trace_id: str
    agent: str
    final_text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw_messages: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic-shaped tool schemas to OpenAI ``functions`` schemas."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


class Agent:
    """Generic LLM agent with a tool-use loop and observability."""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        tools: list[dict[str, Any]],
        tool_funcs: dict[str, Callable[..., dict[str, Any]]],
        model: str | None = None,
        max_iterations: int = 8,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.openai_tools = _to_openai_tools(tools)
        self.tool_funcs = tool_funcs
        self.model = model or settings.openrouter_model
        self.max_iterations = max_iterations
        self.client = (
            OpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
            )
            if settings.openrouter_api_key
            else None
        )

    def run(self, user_message: str, trace_id: str | None = None) -> AgentResult:
        """Run the tool-use loop until the model returns a final answer."""
        if self.client is None:
            return AgentResult(
                trace_id=trace_id or "no-trace",
                agent=self.name,
                final_text="",
                error="OPENROUTER_API_KEY not set",
            )

        trace = trace_id or new_trace_id()
        result = AgentResult(trace_id=trace, agent=self.name, final_text="")
        record_event(trace, self.name, "agent_start", "ok", payload={"user": user_message})

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            for _iteration in range(self.max_iterations):
                t0 = time.perf_counter()
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=2048,
                    messages=messages,  # type: ignore[arg-type]
                    tools=self.openai_tools,  # type: ignore[arg-type]
                    tool_choice="auto",
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                choice = response.choices[0]
                finish_reason = choice.finish_reason
                record_event(
                    trace,
                    self.name,
                    "llm_call",
                    "ok",
                    latency_ms=latency_ms,
                    payload={"finish_reason": finish_reason},
                )

                msg = choice.message
                # Echo the assistant turn back into the conversation. OpenAI's
                # chat format requires the full message (content + tool_calls).
                assistant_turn: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content,
                }
                if msg.tool_calls:
                    assistant_turn["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                messages.append(assistant_turn)

                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        try:
                            tool_args = json.loads(tc.function.arguments or "{}")
                        except json.JSONDecodeError as e:
                            tool_args = {}
                            record_event(
                                trace,
                                self.name,
                                "tool_args_decode_error",
                                "error",
                                tool_name=tc.function.name,
                                payload={"raw": tc.function.arguments, "error": str(e)},
                            )

                        tool_output = self._dispatch_tool(tc.function.name, tool_args, trace)
                        result.tool_calls.append(
                            {
                                "tool": tc.function.name,
                                "input": tool_args,
                                "output": tool_output,
                            }
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": json.dumps(tool_output, default=str),
                            }
                        )
                    continue

                if finish_reason in ("stop", "end_turn", None):
                    result.final_text = msg.content or ""
                    break

                # Unexpected finish reason
                record_event(
                    trace,
                    self.name,
                    "unexpected_finish",
                    "error",
                    payload={"finish_reason": finish_reason},
                )
                result.error = f"unexpected finish_reason: {finish_reason}"
                break
            else:
                result.error = f"hit max_iterations={self.max_iterations}"
                record_event(trace, self.name, "max_iterations", "error")

        except Exception as e:
            result.error = str(e)
            record_event(trace, self.name, "exception", "error", payload={"error": str(e)})
            log.exception("agent_failed", agent=self.name, trace_id=trace)

        record_event(trace, self.name, "agent_end", "ok" if result.error is None else "error")
        return result

    def _dispatch_tool(
        self, tool_name: str, tool_args: dict[str, Any], trace_id: str
    ) -> Any:
        func = self.tool_funcs.get(tool_name)
        if func is None:
            err = f"tool not registered: {tool_name}"
            record_event(
                trace_id,
                self.name,
                "tool_call",
                "error",
                tool_name=tool_name,
                payload={"error": err},
            )
            return {"error": err}

        t0 = time.perf_counter()
        try:
            output = func(**tool_args)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            record_event(
                trace_id,
                self.name,
                "tool_call",
                "ok",
                tool_name=tool_name,
                latency_ms=latency_ms,
                payload={
                    "input": tool_args,
                    "output_keys": list(output.keys()) if isinstance(output, dict) else None,
                },
            )
            return output
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            record_event(
                trace_id,
                self.name,
                "tool_call",
                "error",
                tool_name=tool_name,
                latency_ms=latency_ms,
                payload={"input": tool_args, "error": str(e)},
            )
            return {"error": str(e)}
