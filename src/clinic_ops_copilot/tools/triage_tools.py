"""Tool surface for the Triage agent.

Triage classifies an incoming patient intent (any language), routes to the
correct downstream agent, and escalates to a human when the intent is unclear,
urgent, or out of scope.

The classification is intentionally rule-shaped (keyword + regex) rather than
a separate LLM call. The goal is for the LLM to do the *judgment* (when to
escalate, how to handle code-switching, when to call a clarifying question)
while the deterministic tools provide grounded signals.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Intent keyword tables (English + Spanish + common code-switched fragments)
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: dict[str, list[str]] = {
    "scheduling": [
        # English
        "appointment",
        "book",
        "schedule",
        "reschedule",
        "cancel",
        "available",
        "open slot",
        "next week",
        "tomorrow",
        "today",
        "cleaning",
        "checkup",
        # Spanish
        "cita",
        "agendar",
        "reservar",
        "reprogramar",
        "cancelar",
        "disponible",
        "manana",
        "mañana",
        "hoy",
        "limpieza",
        "chequeo",
        "consulta",
    ],
    "eligibility": [
        # English
        "insurance",
        "coverage",
        "covered",
        "cover",
        "copay",
        "deductible",
        "in network",
        "out of network",
        "prior auth",
        "policy",
        "plan",
        # Spanish
        "seguro",
        "cobertura",
        "cubierto",
        "copago",
        "deducible",
        "red",
        "fuera de red",
        "autorizacion",
        "autorización",
        "póliza",
        "poliza",
    ],
    "billing": [
        # English
        "bill",
        "invoice",
        "payment",
        "charge",
        "claim",
        "balance",
        "owe",
        "refund",
        "statement",
        # Spanish
        "factura",
        "pago",
        "cobro",
        "reclamo",
        "saldo",
        "deuda",
        "reembolso",
        "estado de cuenta",
    ],
    "escalation": [
        # English urgency / out-of-scope cues
        "emergency",
        "urgent",
        "bleeding",
        "severe pain",
        "chest pain",
        "can't breathe",
        "lawsuit",
        "complaint",
        "manager",
        "human",
        "speak to someone",
        # Spanish urgency
        "emergencia",
        "urgente",
        "sangrado",
        "dolor severo",
        "dolor de pecho",
        "no puedo respirar",
        "queja",
        "humano",
        "persona",
    ],
}

# Spanish detection: characters and stopwords that strongly suggest Spanish
SPANISH_HINTS = re.compile(
    r"\b(el|la|los|las|de|del|que|por|para|con|sin|tengo|necesito|quiero|"
    r"hola|gracias|hoy|mañana|manana|cita|seguro|hola|dolor|dentista|doctor)\b",
    re.IGNORECASE,
)
SPANISH_CHARS = re.compile(r"[ñáéíóúü¡¿]", re.IGNORECASE)

ENGLISH_HINTS = re.compile(
    r"\b(the|a|an|of|to|and|is|i|you|we|need|want|book|appointment|tomorrow|"
    r"today|insurance|hello|thanks|pain|dentist|doctor)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def classify_intent(text: str) -> dict[str, Any]:
    """Classify a patient utterance into an intent class and detect language.

    Returns scores per class so the agent can decide whether the top match is
    confident or whether to ask for clarification. Plugin-contributed keywords
    (via INTENT_KEYWORDS in plugin files) are merged in automatically.
    """
    # Merge built-in keywords with any plugin contributions
    all_keywords: dict[str, list[str]] = {k: list(v) for k, v in INTENT_KEYWORDS.items()}
    try:
        from clinic_ops_copilot.agents.registry import registry

        for cls, kws in registry.extra_keywords().items():
            all_keywords.setdefault(cls, []).extend(kws)
    except ImportError:
        pass

    lower = text.lower()
    scores: dict[str, int] = dict.fromkeys(all_keywords, 0)
    matched: dict[str, list[str]] = {k: [] for k in all_keywords}

    for cls, keywords in all_keywords.items():
        for kw in keywords:
            if kw in lower:
                scores[cls] += 1
                matched[cls].append(kw)

    top_class = max(scores, key=lambda k: scores[k])
    top_score = scores[top_class]

    # Language detection
    es_hits = len(SPANISH_HINTS.findall(text)) + (2 if SPANISH_CHARS.search(text) else 0)
    en_hits = len(ENGLISH_HINTS.findall(text))

    if es_hits > 0 and en_hits > 0 and abs(es_hits - en_hits) <= 1:
        language = "mixed"
    elif es_hits > en_hits:
        language = "es"
    elif en_hits > 0:
        language = "en"
    else:
        language = "unknown"

    confidence = "high" if top_score >= 2 else ("low" if top_score == 1 else "none")

    return {
        "top_class": top_class if top_score > 0 else "unknown",
        "top_score": top_score,
        "confidence": confidence,
        "language": language,
        "scores": scores,
        "matched_keywords": {k: v for k, v in matched.items() if v},
    }


def route_to_agent(intent_class: str) -> dict[str, Any]:
    """Resolve an intent_class to a downstream agent.

    Checks the agent registry first so dynamically registered plugins are
    valid routing targets. Falls back to hardcoded built-in routes so this
    function works in test contexts where the registry is not populated.
    """
    if intent_class == "escalation":
        return {"routed": True, "intent_class": intent_class, "target": "human"}

    # Check registry for registered agents (built-ins + plugins)
    try:
        from clinic_ops_copilot.agents.registry import registry

        if intent_class in registry.names():
            return {"routed": True, "intent_class": intent_class, "target": intent_class}
    except ImportError:
        pass

    # Fallback for test contexts where registry is not populated
    _fallback: dict[str, str] = {"scheduling": "scheduler", "eligibility": "eligibility"}
    if intent_class in _fallback:
        return {"routed": True, "intent_class": intent_class, "target": _fallback[intent_class]}

    return {"routed": False, "reason": f"unknown intent_class: {intent_class}"}


def escalate_to_human(reason: str, urgency: str = "normal") -> dict[str, Any]:
    """Escalate the conversation to a human at the front desk."""
    if urgency not in ("normal", "high", "emergency"):
        urgency = "normal"
    return {
        "escalated": True,
        "destination": "front_desk",
        "urgency": urgency,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Tool dispatch table + JSON schemas exposed to the LLM
# ---------------------------------------------------------------------------


TRIAGE_TOOL_FUNCS = {
    "classify_intent": classify_intent,
    "route_to_agent": route_to_agent,
    "escalate_to_human": escalate_to_human,
}


TRIAGE_TOOLS = [
    {
        "name": "classify_intent",
        "description": (
            "Classify a patient utterance into one of: scheduling, eligibility, "
            "billing, escalation. Also detects language (en/es/mixed). Returns "
            "scores per class so you can decide if the top match is confident."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Raw patient utterance, in any language",
                }
            },
            "required": ["text"],
        },
    },
    {
        "name": "route_to_agent",
        "description": "Resolve an intent_class to its downstream agent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "intent_class": {
                    "type": "string",
                    "description": "The intent class to route to",
                }
            },
            "required": ["intent_class"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Escalate to a human at the front desk. Use for emergencies, "
            "ambiguous intents, complaints, or anything outside Phase 1 scope."
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
    },
]


def build_triage_tool_surface(
    agent_names: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return a (tools, tool_funcs) pair with the route_to_agent enum built
    from the currently registered agent names.

    Called by build_triage_agent() so the tool schema always reflects whatever
    agents are registered at startup (built-ins + plugins).
    """
    valid_classes = [*agent_names, "escalation"]

    tools = [
        TRIAGE_TOOLS[0],  # classify_intent — static
        {
            "name": "route_to_agent",
            "description": "Resolve an intent_class to its downstream agent.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "intent_class": {
                        "type": "string",
                        "enum": valid_classes,
                        "description": "The intent class to route to",
                    }
                },
                "required": ["intent_class"],
            },
        },
        TRIAGE_TOOLS[2],  # escalate_to_human — static
    ]
    return tools, TRIAGE_TOOL_FUNCS
