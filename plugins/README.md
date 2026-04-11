# ClinicOps Plugins

Drop a `.py` file in this directory and it is automatically discovered and registered as an agent when `clinicops chat` starts.

## Quickstart

Copy an example, fill in the TODOs, and you're done:

```bash
cp _prior_auth_example.py prior_auth.py
# edit prior_auth.py — fill in the tool implementations
clinicops chat "Does patient 123 need prior auth for a knee replacement?"
```

## Plugin contract

A plugin file must define three things:

```python
# 1. Unique agent name (used for routing)
AGENT_NAME = "prior_auth"

# 2. One-line description (shown to Triage so it knows when to route here)
AGENT_DESCRIPTION = "Checks prior authorization requirements and status."

# 3. Factory function that returns a configured Agent
def build_agent():
    from clinic_ops_copilot.agents.base import Agent
    return Agent(
        name=AGENT_NAME,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_funcs=TOOL_FUNCS,
    )
```

## Optional: intent keywords

Define `INTENT_KEYWORDS` to help the keyword classifier route to your agent:

```python
INTENT_KEYWORDS = {
    "prior_auth": [
        "prior auth", "pre-authorization", "auth status",
        "autorización previa",  # Spanish supported
    ]
}
```

Without this, Triage can still route to your agent based on the system prompt
context — but explicit keywords improve confidence scores.

## File naming

| Filename | Behaviour |
|---|---|
| `prior_auth.py` | Loaded and registered on startup |
| `_prior_auth_example.py` | **Skipped** — leading `_` marks it as a draft/example |

Rename a file to activate or deactivate it. No core code changes needed.

## Plugin structure reference

```python
AGENT_NAME = "my_agent"           # str, required
AGENT_DESCRIPTION = "..."         # str, required
INTENT_KEYWORDS = {...}           # dict[str, list[str]], optional

SYSTEM_PROMPT = "..."             # str

def my_tool(param: str) -> dict:
    ...

TOOLS = [                         # list of Anthropic-format tool schemas
    {
        "name": "my_tool",
        "description": "...",
        "input_schema": {
            "type": "object",
            "properties": {"param": {"type": "string"}},
            "required": ["param"],
        },
    }
]

TOOL_FUNCS = {"my_tool": my_tool} # dispatch table

def build_agent():                # required
    from clinic_ops_copilot.agents.base import Agent
    return Agent(
        name=AGENT_NAME,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_funcs=TOOL_FUNCS,
    )
```

## Available workflow categories

Common clinical ops categories you might build plugins for:

| Category | What it handles |
|---|---|
| Prior Authorization | Pre-approval checks, auth status tracking |
| Referral Management | Specialist referrals, referral status |
| Lab Results | Abnormal value flagging, provider notification |
| Medication Management | Refill requests, drug prior auth |
| Billing / RCM | Claim status, denial classification |
| Patient Outreach | Reminders, follow-up communication |
| Discharge Planning | Post-care coordination |
