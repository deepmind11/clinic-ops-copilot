"""Agent registry — single source of truth for all agents (built-in + plugins).

Built-in agents (Scheduler, Eligibility) are registered explicitly at CLI
startup. Plugin agents are discovered from the ``plugins/`` directory at the
same time. Triage reads the registry when it is built so its system prompt and
routing table always reflect whatever agents are currently registered.
"""

from __future__ import annotations

import importlib.util
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from clinic_ops_copilot.agents.base import Agent


@dataclass
class AgentRegistration:
    name: str
    description: str
    factory: Callable[[], Agent]
    intent_keywords: dict[str, list[str]] = field(default_factory=dict)


class AgentRegistry:
    """Holds all registered agents and handles plugin discovery."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentRegistration] = {}

    def register(
        self,
        name: str,
        description: str,
        factory: Callable[[], Agent],
        intent_keywords: dict[str, list[str]] | None = None,
    ) -> None:
        """Register an agent by name."""
        self._agents[name] = AgentRegistration(
            name=name,
            description=description,
            factory=factory,
            intent_keywords=intent_keywords or {},
        )

    def discover(self, plugins_dir: Path) -> list[str]:
        """Scan plugins_dir for .py plugin files and register valid ones.

        A valid plugin must define:
          - AGENT_NAME: str
          - AGENT_DESCRIPTION: str
          - build_agent() -> Agent

        Optionally it may define:
          - INTENT_KEYWORDS: dict[str, list[str]]  (extra classification hints)

        Files starting with ``_`` are skipped — use this for examples and drafts.
        Returns a list of successfully loaded agent names.
        """
        loaded: list[str] = []
        if not plugins_dir.exists():
            return loaded

        for path in sorted(plugins_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"clinicops_plugin_{path.stem}", path)
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                if not (
                    hasattr(mod, "AGENT_NAME")
                    and hasattr(mod, "AGENT_DESCRIPTION")
                    and hasattr(mod, "build_agent")
                ):
                    continue
                self.register(
                    name=mod.AGENT_NAME,
                    description=mod.AGENT_DESCRIPTION,
                    factory=mod.build_agent,
                    intent_keywords=getattr(mod, "INTENT_KEYWORDS", None),
                )
                loaded.append(mod.AGENT_NAME)
            except Exception as exc:
                warnings.warn(f"Failed to load plugin {path.name}: {exc}", stacklevel=2)

        return loaded

    def get(self, name: str) -> AgentRegistration | None:
        return self._agents.get(name)

    def all(self) -> dict[str, AgentRegistration]:
        return dict(self._agents)

    def names(self) -> list[str]:
        return list(self._agents.keys())

    def extra_keywords(self) -> dict[str, list[str]]:
        """Collect intent keywords contributed by all plugin registrations."""
        merged: dict[str, list[str]] = {}
        for reg in self._agents.values():
            for cls, kws in reg.intent_keywords.items():
                merged.setdefault(cls, []).extend(kws)
        return merged


# Module-level singleton — populated at CLI startup before Triage is built.
registry = AgentRegistry()


def register_builtins() -> None:
    """Register the built-in Scheduler and Eligibility agents on the singleton.

    Idempotent: calling twice is a no-op. Shared by the CLI startup and the
    eval runner so the master agent always sees the built-ins as delegate tools.
    """
    from clinic_ops_copilot.agents.eligibility import build_eligibility_agent
    from clinic_ops_copilot.agents.scheduler import build_scheduler_agent

    if "scheduler" not in registry.names():
        registry.register(
            "scheduler",
            "Books, reschedules, and cancels patient appointments.",
            build_scheduler_agent,
        )
    if "eligibility" not in registry.names():
        registry.register(
            "eligibility",
            "Checks patient insurance coverage and prior authorization requirements.",
            build_eligibility_agent,
        )
