# ClinicOps Plugins

Drop a `.py` file in this directory and it is automatically discovered at startup and becomes a new `delegate_to_<name>` tool on the ClinicOps Assistant. No core code changes, no prompt edits.

## How plugins fit into the architecture

ClinicOps uses an **agents-as-tools** pattern: the patient talks to one user-facing assistant (the "master"), which delegates specialized work to sub-agents via `delegate_to_<name>` tool calls. Plugins are just sub-agents that the registry picks up at startup. When you add a plugin named `prior_auth`, the master automatically gains a `delegate_to_prior_auth` tool and starts routing relevant requests to it.

## Quickstart

Copy an example, fill in the TODOs, and you're done:

```bash
cp _prior_auth_example.py prior_auth.py
# edit prior_auth.py — fill in the tool implementations
uv run clinicops
> Does patient pat-00042 need prior auth for a knee replacement?
```

## Plugin contract

A plugin file must define three things:

```python
# 1. Unique agent name (becomes delegate_to_<AGENT_NAME> on the master)
AGENT_NAME = "prior_auth"

# 2. One-line description (shown to the master so it knows when to delegate here)
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

Define `INTENT_KEYWORDS` to contribute keywords to the deterministic `classify_intent` utility function. These are useful for eval cases and any keyword-based classification done outside the master agent:

```python
INTENT_KEYWORDS = {
    "prior_auth": [
        "prior auth", "pre-authorization", "auth status",
        "autorización previa",  # Spanish supported
    ]
}
```

The master agent itself routes based on `AGENT_DESCRIPTION` and the user's intent, not on these keywords — but a well-chosen description is what drives good routing.

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
