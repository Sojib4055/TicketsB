# ticket-bot-mcp

A **safe starter template** for a ticket-monitoring and checkout assistant using:
- a deterministic state machine
- confidence-scored parsing
- business policy guardrails and offer scoring
- adaptive single-page or multi-page monitoring
- MCP-compatible browser automation
- explainable human handoff for sensitive steps

This template is intentionally conservative:
- no stealth plugin
- no CAPTCHA bypass
- dry-run mode enabled by default
- payment execution is guarded by policy checks and human confirmation hooks

## Project goals

1. Monitor an event page for availability changes
2. Parse page state into a structured status
3. Require confidence thresholds and confirming snapshots before acting
4. Use MCP browser tools through a wrapper layer
5. Rank valid offers using hard policy constraints plus soft preferences
6. Log every action and keep screenshots / audit events
7. Stop immediately if price caps or business rules are violated

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
npx @playwright/mcp@latest --port 8931
```

The app expects streamable HTTP transport and connects to `MCP_SERVER_URL`, which defaults to `http://localhost:8931/mcp`.

### 3) Run the app
```bash
python -m src.main
```

The app starts a local dashboard and prints its URL, for example:

```text
Dashboard: http://127.0.0.1:8765
```

Open that URL to see live monitor status, top ranked offers, policy decisions,
price/seat changes, screenshots, and the final decision brief. The process keeps
serving the dashboard after the run reaches a final state; press `Ctrl+C` in the
terminal when you are done viewing it.

## Notes

- `src/browser/session.py` contains a thin wrapper where you can connect your MCP client implementation.
- `src/monitoring/availability_parser.py` converts text / snapshot output into structured states.
- `src/monitoring/scheduler.py` adapts polling delay per target based on status and belief score.
- `src/monitoring/extractors/` contains the regex fast path and a semantic extraction hook.
- `src/policy.py` contains hard limits plus offer ranking metadata.
- `src/analytics/` reads audit events back for drop-window and site-reliability summaries.
- `src/ui/` serves the local browser dashboard.
- `src/reports/` writes `logs/reports/latest_offer_report.json` and `.txt`.
- `DRY_RUN=true` is recommended until you fully test your flow.
- Use `MAX_TOTAL_PRICE` and `PRICE_CURRENCY` for the active site. `MAX_TOTAL_USD` is still accepted for backward compatibility.

## Ranking preferences

Optional scoring preferences:

```bash
PREFERRED_OPERATORS=SHYAMOLI PARIBAHAN,Hanif Enterprise
AVOID_OPERATORS=
PREFERRED_DEPARTURE_START=12:00 PM
PREFERRED_DEPARTURE_END=06:00 PM
AVOID_NIGHT_BUSES=true
TARGET_ORIGIN=Dhaka
TARGET_DESTINATION=Bogura
```

The scorer still enforces hard limits first: max tickets, max total price,
blocked keywords, avoided operators, and non-positive fares.

## Multi-target monitoring

By default the app monitors `TARGET_EVENT_URL`. To monitor multiple pages, set
`MONITOR_TARGETS_JSON` to a JSON list:

```bash
MONITOR_TARGETS_JSON='[
  {"id":"event-a","url":"https://example.com/a","label":"Event A","priority":1.0},
  {"id":"event-b","url":"https://example.com/b","label":"Event B","priority":1.5,"poll_min_seconds":5,"poll_max_seconds":45}
]'
```

The scheduler polls higher-belief targets more aggressively and backs off after repeated sold-out snapshots.
