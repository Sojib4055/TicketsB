# ticket-bot-mcp

A **safe starter template** for a ticket-monitoring and checkout assistant using:
- a deterministic state machine
- business policy guardrails
- MCP-compatible browser automation
- human handoff for sensitive steps

This template is intentionally conservative:
- no stealth plugin
- no CAPTCHA bypass
- dry-run mode enabled by default
- payment execution is guarded by policy checks and human confirmation hooks

## Project goals

1. Monitor an event page for availability changes
2. Parse page state into a structured status
3. Decide the next action using a planner + state machine
4. Use MCP browser tools through a wrapper layer
5. Log every action and keep screenshots / audit events
6. Stop immediately if price caps or business rules are violated

## Quick start

### 1) Create environment
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2) Start the Playwright MCP server
In your MCP host or compatible IDE, use the included `mcp_config.json`.

If you want to run the server manually:
```bash
npx @playwright/mcp@latest
```

### 3) Run the app
```bash
python -m src.main
```

## Notes

- `src/browser/session.py` contains a thin wrapper where you can connect your MCP client implementation.
- `src/monitoring/availability_parser.py` converts text / snapshot output into structured states.
- `src/policy.py` contains the hard limits.
- `DRY_RUN=true` is recommended until you fully test your flow.
