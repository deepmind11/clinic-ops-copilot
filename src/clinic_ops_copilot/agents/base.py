"""Shared agent runner built on the Anthropic SDK.

We deliberately use the anthropic Python SDK directly rather than a higher-
level agent framework. The SDK's tool-use loop is stable, well-documented,
and gives us full control over observability instrumentation. Each agent
just supplies a system prompt, a tool schema list, and a tool dispatch
table; the runner handles the rest.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from anthropic import Anthropic
from anthropic.types import Message, MessageParam, ToolUseBlock

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


class Agent:
    """Generic Claude agent with tool-use loop and observability."""

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
        self.tool_funcs = tool_funcs
        self.model = model or settings.anthropic_model
        self.max_iterations = max_iterations
        self.client = (
            Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
        )

    def run(self, user_message: str, trace_id: str | None = None) -> AgentResult:
        """Run the tool-use loop until the model returns a final answer."""
        if self.client is None:
            return AgentResult(
                trace_id=trace_id or "no-trace",
                agent=self.name,
                final_text="",
                error="ANTHROPIC_API_KEY not set",
            )

        trace = trace_id or new_trace_id()
        result = AgentResult(trace_id=trace, agent=self.name, final_text="")
        record_event(trace, self.name, "agent_start", "ok", payload={"user": user_message})

        messages: list[MessageParam] = [{"role": "user", "content": user_message}]

        try:
            for _iteration in range(self.max_iterations):
                t0 = time.perf_counter()
                response: Message = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=self.system_prompt,
                    tools=self.tools,  # type: ignore[arg-type]
                    messages=messages,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                record_event(
                    trace,
                    self.name,
                    "llm_call",
                    "ok",
                    latency_ms=latency_ms,
                    payload={"stop_reason": response.stop_reason},
                )

                # Append assistant turn (full content blocks, not just text)
                messages.append({"role": "assistant", "content": response.content})  # type: ignore[typeddict-item]

                if response.stop_reason == "end_turn":
                    text_parts = [
                        b.text for b in response.content if getattr(b, "type", None) == "text"
                    ]
                    result.final_text = "\n".join(text_parts)
                    break

                if response.stop_reason == "tool_use":
                    tool_results = []
                    for block in response.content:
                        if not isinstance(block, ToolUseBlock):
                            continue
                        tool_result = self._dispatch_tool(block, trace)
                        result.tool_calls.append(
                            {
                                "tool": block.name,
                                "input": block.input,
                                "output": tool_result,
                            }
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": str(tool_result),
                            }
                        )
                    messages.append({"role": "user", "content": tool_results})  # type: ignore[typeddict-item]
                    continue

                # Unexpected stop reason
                record_event(
                    trace,
                    self.name,
                    "unexpected_stop",
                    "error",
                    payload={"stop_reason": response.stop_reason},
                )
                result.error = f"unexpected stop_reason: {response.stop_reason}"
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

    def _dispatch_tool(self, block: ToolUseBlock, trace_id: str) -> Any:
        func = self.tool_funcs.get(block.name)
        if func is None:
            err = f"tool not registered: {block.name}"
            record_event(
                trace_id,
                self.name,
                "tool_call",
                "error",
                tool_name=block.name,
                payload={"error": err},
            )
            return {"error": err}

        t0 = time.perf_counter()
        try:
            assert isinstance(block.input, dict)
            output = func(**block.input)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            record_event(
                trace_id,
                self.name,
                "tool_call",
                "ok",
                tool_name=block.name,
                latency_ms=latency_ms,
                payload={
                    "input": block.input,
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
                tool_name=block.name,
                latency_ms=latency_ms,
                payload={"input": block.input, "error": str(e)},
            )
            return {"error": str(e)}
