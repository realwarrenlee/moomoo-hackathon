# MooTrade

**A Qoder-native autonomous paper-trading control centre for the 2026 Moomoo × Qoder AI Trading Agent Challenge.**

> An AI trading team that doesn't just know when to trade. It knows when to stop.

**Status:** local mock safety core, a **verified local read-only Moomoo REST transport**, a **six-page read-only MooTrade dashboard**, and one active S&P 500 directional research strategy, **`spy-directional`**. It evaluates completed SPY daily bars once per session and selects SPY, UPRO, SH, SPXU or CASH through fixed rules. The implementation is **read-only**: the production allowlist is unchanged (`SPY`, `QQQ`, `IWM`), so SH/UPRO/SPXU proposals are rejected at `R002`; leveraged orders additionally require the opt-in `R015` gate, and `ORDER_WRITES_ENABLED=false`. The separately approved first diagnostic paper BUY/SELL verification remains pending and was not changed by this work.

The competition paper account `****0101` (`account_type=2`, `market_id=100`, title and fingerprint match) was verified at 100,000 USD cash/equity with zero positions or orders through the local OAuth 2.1 + PKCE REST client. Read and execution tokens remain DPAPI-encrypted outside the repository; the read token has no `trade:write`. The documented simulated-order transport and supervised CLI remain disabled by default and require two explicit flags, a durable approval and every preflight check; **no order endpoint has been contacted and no order has been submitted**. Qoder Cloud Agent v4 keeps `always_deny` on all order-writing MCP tools. A genuine current-market three-agent run under `spy-directional` completed on 18 November 2026 and produced a policy-rejected SH proposal; earlier runs are retained as historical evidence. See [`docs/strategy-and-risk.md`](docs/strategy-and-risk.md) and [`docs/integrations.md`](docs/integrations.md).

## What judges will see

A desktop-first web dashboard showing (1) paper account equity, cash and exposure; (2) Qoder Cloud Agent runs; (3) research evidence and trade proposals; (4) deterministic risk decisions; (5) broker order and fill state from reconciliation (currently empty); and (6) portfolio reconciliation, incidents and performance.

The target demo is **one traceable decision from market data through Qoder agents to a broker-confirmed paper outcome**, plus a safe test showing a rejected oversized order never reaches the broker. No broker-confirmed order or fill exists yet.

## Read these in order

1. [`plan.md`](plan.md) — goals, rubric, scope and timeline.
2. [`docs/architecture.md`](docs/architecture.md) — trust boundaries, data flow and services.
3. [`docs/strategy-and-risk.md`](docs/strategy-and-risk.md) — the active `spy-directional` rules, RiskGate policy and required tests.
4. [`docs/operations.md`](docs/operations.md) — install, verify, run, supervise and recover.
5. [`docs/evidence.md`](docs/evidence.md) — demonstrated achievements, evidence matrix, and what remains unverified.
6. [`docs/reusability.md`](docs/reusability.md) — reusable modules, contracts and extension points.
7. [`docs/integrations.md`](docs/integrations.md) — what the owner must set up, what is verified, and what remains blocked.
8. [`docs/dashboard.md`](docs/dashboard.md) — six pages, read-only API, provenance and states.
9. [`docs/build-checklist.md`](docs/build-checklist.md) — sequenced deliverables and acceptance gates.
10. [`docs/judge-demo.md`](docs/judge-demo.md) — evidence and submission rehearsal.
11. [`AGENTS.md`](AGENTS.md) — constraints for the coding agent.

## Stack

- Qoder Cloud Agents: a coordinator, a researcher and an independent risk auditor, all read-only. Signal arithmetic, sizing, the `RiskGate` and the supervised order command are deterministic Python.
- Moomoo competition paper account: local OAuth 2.1 + PKCE REST reads for quotes, account state and order history. The simulated-order transport is disabled by default and reachable only through the operator-only supervised CLI.
- Python + FastAPI + Pydantic: API, broker adapter, deterministic risk policy and reconciler.
- SQLite on durable storage: append-only audit events and state records; migrate if hosting requires it.
- Next.js + TypeScript + Tailwind/shadcn/ui: dashboard, **conditionally adapted from the Shadcn Fintech template** after licensing and dependency checks.
- pytest: mocked broker/agent failures, policy and reconciliation tests.

No live-money trading, no secrets in source control, no autonomous execution before the account and permissions are verified.

## Working order

**Integration discovery → read-only account sync → policy and audit ledger → one controlled paper order → Qoder scheduling → dashboard → evidence → deck.**

The dashboard must never show fictional account values as real. All mock data is visibly labelled and isolated from the live competition paper-account view.

## Local mock core

The backend contains an exact competition-account lock (masked id + SHA-256 fingerprint, simulated source only), validated trading contracts, the deterministic `risk-v1` gate, a paper-only mock broker, an append-only SQLite event ledger, durable submission idempotency, a persistent kill switch, durable first-order approval and an enforced order state machine. The gate is cash-only and enforces 10% per position, 30% total exposure, 3 open positions and 2% daily equity drawdown. It rejects missing, stale or invalid quotes/account data and fails closed on broker read failures. The local execution path covers approval, rejection, acknowledgement, full and partial fills, ambiguous timeouts and reconciliation events.

`backend/app/broker/moomoo_readonly.py` adds a read-only adapter over an injected MCP tool caller. It can invoke only `sim_trade_account_list`, `sim_trade_cash_info`, `sim_trade_position_list` and `sim_trade_history_order_list`; it rejects every other tool name before the caller, including all ten order-writing tools. It resolves the exact competition account through the existing lock, converts cash/positions/orders into `AccountSnapshot`, persists the daily equity baseline in SQLite, ignores margin buying power (`max_power_long`) for cash-only sizing, and has no order-submission method. The earlier Python-to-cloud-MCP bridge remains unavailable because vault secrets are injection-only, so that adapter is still fixture-tested. `moomoo_auth.py` and `moomoo_rest.py` now provide a separate local OAuth 2.1 + PKCE read path with DPAPI token storage and GET-only allowlisted sim-trade endpoints, plus two documented POST-for-read quote endpoints; it verified the same competition account and state against the real provider. `moomoo_quotes.py` adds execution-time quote freshness, symbol and regular-session checks. `moomoo_orders.py` adds a documented simulated-order payload builder, bounded `text` correlation tag, strict status mapping, `UNKNOWN` reconciliation from today's orders/history/positions, and a guarded `MoomooOrderTransport` that can POST only to `/api/v1.0/sim-trade/{acc_id}/orders`. The transport is disabled by default, never retries, and converts any unclear response into `UNKNOWN`; `MoomooPaperBroker` composes it with the read adapter and existing controls. No runtime path enables writes, no real paper order has been submitted, and the REST read client still explicitly rejects order submission.

### Local read-only Moomoo REST

```bash
.venv/Scripts/python -m app.cli moomoo-login
.venv/Scripts/python -m app.cli moomoo-auth-status
.venv/Scripts/python -m app.cli moomoo-read
.venv/Scripts/python -m app.cli moomoo-preview-order --symbol QQQ --action BUY --quantity 1 --proposal-id preview-1
.venv/Scripts/python -m app.cli moomoo-execution-login
.venv/Scripts/python -m app.cli moomoo-execution-status
.venv/Scripts/python -m app.cli moomoo-execution-check
```

Complete browser consent with read permissions only for `moomoo-login`; do not grant `trade:write` there. `moomoo-preview-order` performs a fresh quote/session read with the read token, evaluates the deterministic gate and prints the documented payload, risk reasons and safety checks; `submission_performed` is always `false`. `moomoo-execution-login` is a separate client and token file for a supervised order; it requests `quote:read trade:read trade:write` and warns that account-exclusive write scope is unverified. `moomoo-execution-check` uses read-only calls and confirms the account but never contacts an order endpoint. `moomoo-read` prints sanitized `PAPER` JSON with account identity, cash, positions, open orders, paginated history, timestamps and reconciliation. The sim-account token may show `quote:read` plus an `accid:` binding instead of a literal `trade:read`; the validator accepts that read-equivalent binding and rejects any `trade:write` grant. Both tokens are stored in DPAPI-encrypted files outside the repository.

Once the execution token exists, `moomoo-supervised-preview` evaluates an exact order through the execution client with writes hypothetically enabled but no submission. `moomoo-supervised-execute` is the only write-capable command: it additionally requires `--enable-order-writes`, the exact `--confirm-client-order-key`, a durable approval bound to that proposal, a fresh regular-session quote, a reconciled competition account, a clean kill switch and every `RiskGate` rule. It submits at most once, never retries an ambiguous outcome, and reconciles once read-only. `moomoo-supervised-reconcile` only reads. An execution token now exists; no order has been submitted.

## Research pipeline: `spy-directional`

`backend/app/research/` implements one active strategy over completed daily bars, with no look-ahead:

1. Each completed session computes SPY's 10-session return, 50-session SMA and 20-session annualised realised volatility from provider bars.
2. **BULLISH** requires a 10-session return of at least `+1.5%` and SPY above its SMA50. **BEARISH** requires at most `-1.5%` and SPY below its SMA50. Anything else is **NEUTRAL**. Annualised volatility above `40%` forces CASH.
3. The fixed universe is SPY (`+1x`), UPRO (`+3x`), SH (`-1x`) and SPXU (`-3x`). Inverse exposure uses inverse ETFs bought with `BUY` orders, never short-selling.
4. A `STRONG BULLISH`/`STRONG BEARISH` label requires an absolute 10-session return of at least `3.0%` and volatility at or below `30%`. It can select UPRO/SPXU only when leverage is separately enabled; otherwise it selects SPY/SH.
5. Target size is `5%` effective exposure; 3x quantity is floored from `equity × 5% / (price × 3)`. A matching holding produces HOLD; a neutral signal or non-matching target produces CASH or a SELL. A reversal is entered only by a later run after the broker confirms the old position is flat.
6. The existing `RiskGate` is final. `R015` blocks leveraged instruments unless explicitly opted in, and the production allowlist remains `SPY`/`QQQ`/`IWM`, so SH/UPRO/SPXU proposals fail closed with `R002` until separately approved.

The exact policy, state transitions and limitations are in [`docs/strategy-and-risk.md`](docs/strategy-and-risk.md).

**Evidence status:** real read-only Moomoo bars cover 370 sessions through 17 November 2026 for all four ETFs. The latest completed-session decision was BEARISH at close `732.44` (10-session return `-2.90%`, SMA50 `762.89`, volatility `23.06%`), targeting SH with a 147-share, 5% BUY proposal. Real `RiskGate` rejected it for `R002`, stale post-close quote, non-regular session, disabled writes and missing first-order approval. The one historical sanity run from 12 August 2025 to 17 November 2026 returned `-0.40%`, `0.42%` annualised volatility, `0.59%` maximum drawdown, `41%` of sessions exposed, 35 trades and a `41.18%` win rate, versus SPY buy-and-hold at `+15.47%`. That is a fixed-rule sanity check, **not evidence of alpha, not an optimised result and not a paper-account result**.

Retired strategies (`momentum-v1`, `news-catalyst-v1`, `directional-event-v2`, the stock-selection pre-registration, the Moomoo oversold-reversal candidate and the ETF trend baseline) are no longer registered or active. Their prior reports and event evidence remain under `evidence/` as historical research. The event archive, event module and synthetic event fixture were removed.

Run the focused research and gate tests:

```bash
cd backend
../.venv/Scripts/python -m pytest tests/test_research.py tests/test_qoder_tools.py tests/test_risk.py -q
```

A genuine read-only three-agent run uses the same fixed tool boundary and prints its report path; it cannot submit an order. Add `--decision-time` to pin a historical session for a reproducible demo; omit it to evaluate the latest decision:

```bash
cd backend
../.venv/Scripts/python -m scripts.qoder_readonly_run \
  --workspace-id "$QODER_WORKSPACE_ID" \
  --environment-id "$QODER_ENVIRONMENT_ID" \
  --coordinator-agent-id "$QODER_COORDINATOR_AGENT_ID" \
  --researcher-agent-id "$QODER_RESEARCHER_AGENT_ID" \
  --auditor-agent-id "$QODER_AUDITOR_AGENT_ID" \
  --decision-time 2026-10-13T21:00:00Z
```

The current-market runner uses the same strategy and live read-only Moomoo account/quote feeds; it also has no order path.

## Qoder read-only orchestration

The workflow uses exactly three Qoder Cloud Agents: a **coordinator** that validates the run boundary and closes the report, a **researcher** that calls `research_market`, and an independent **risk auditor** that challenges the evidence and calls `evaluate_proposal` only when a proposal exists. The coordinator has no tools; none of the agents has an order path. On 18 November 2026 the deployed researcher agent was updated to version 4, replacing the retired `directional-event-v2` enum with `spy-directional`. A genuine current-market three-agent run then completed for run `qoder-328aefff-7dde-4a98-ac76-99b3e0e33728`:

- coordinator `sess_00vuffkjlafwgresy62p`
- researcher `sess_00vuffpgw47pdzx2s53d`
- auditor `sess_00vufg56d34sgybrbybv`

The researcher called `research_market` once on real Moomoo bars through 17 November 2026. Its sanitized artifact records a BEARISH signal at `732.44`, a 10-session return of `-2.90%`, SMA50 `762.89`, volatility `23.06%`, deterministic selection of SH at 1x and a 147-share BUY proposal. The auditor called `evaluate_proposal` once; the real `RiskGate` rejected it for `R002` (SH outside the production allowlist), stale post-close quote, non-regular session, disabled writes (`R010`) and missing first-order approval (`R014`). The coordinator closed the run with outcome `POLICY_REJECTED`; no order was created or filled. Evidence: [`evidence/qoder/qoder-328aefff-7dde-4a98-ac76-99b3e0e33728.md`](evidence/qoder/qoder-328aefff-7dde-4a98-ac76-99b3e0e33728.md).

The earlier event-strategy runs are retained under `evidence/qoder/` as historical execution evidence, not as current `spy-directional` results. The local runner enforces strict tool inputs, pinned run state and one tool result per call, and does not retry ambiguous delivery.

Qoder Cloud Agents remain the research and audit layer, not the broker transport. Authenticated competition-account reads use the separate local REST client; no agent has an order path. The execution architecture, remaining blockers and acceptance tests are recorded in [`docs/integrations.md`](docs/integrations.md).

## Read-only dashboard and API

The dashboard is an adapted copy of the Shadcn Fintech template (MIT, attribution in [`frontend/ATTRIBUTION.md`](frontend/ATTRIBUTION.md)) with six desktop-first pages: Overview (`/dashboard`), AI Agent Activity (`/agents`), Portfolio & Orders (`/portfolio`), Risk Centre (`/risk`), Performance Analytics (`/analytics`) and Audit Log (`/audit`). It shows only backend-computed values; the browser never receives OAuth credentials, account fingerprints or PATs. PAPER mode is displayed by the persistent sidebar `Writes DISABLED` indicator and per-block provenance labels that separate live broker reads, local ledger/controls, the recorded historical Qoder run and historical strategy curves. Paper-account performance is explicitly unavailable because there are no fills.

The FastAPI app exposes seven GET-only routes (`/api/v1/health`, `/overview`, `/portfolio`, `/risk`, `/agents`, `/analytics`, `/audit`) plus OpenAPI docs. Non-GET requests return 405, the server refuses to start with writes enabled, and access requires either an optional `MOOTRADE_DASHBOARD_TOKEN` bearer token or a loopback client. The Next.js server proxy allowlists the same seven paths (six pages plus health). Details: [`docs/dashboard.md`](docs/dashboard.md).

```bash
# Terminal 1 — read-only API
cd backend && ../.venv/Scripts/python -m uvicorn app.dashboard.api:app --host 127.0.0.1 --port 8000
# Terminal 2 — dashboard
cd frontend && npx --yes pnpm@10 install --frozen-lockfile && npx --yes pnpm@10 dev
```

### Setup and tests

Requires Python 3.11+. From the repository root on Windows:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

On macOS/Linux, use `.venv/bin/python` instead. **Verified on 18 November 2026 with Python 3.14.5: 310 backend tests passed**, including REST OAuth, execution-scope validation, registration-only status rejection, REST read transport, disabled order-transport success/partial/rejection/timeout/duplicate/`UNKNOWN` mocks, supervised CLI missing-approval/kill-switch/wrong-account/closed-market/ambiguous guards, execution preflight/correlation/reconciliation, CLI, Qoder runner/tool, four-ETF SPY selection/HOLD/CASH/reversal, leverage-aware RiskGate, ETF baseline, scheduler catch-up/idempotency/interruption recovery, clock-skew handling and dashboard API tests. The dashboard also passed 17 formatting regression tests, TypeScript typecheck, ESLint and `next build`. The authenticated REST account reads are real provider evidence; the remaining tests are unit, fixture and mock results. No fill or order result has been observed.

### First-order approval (operator action, never submits an order)

```bash
.venv/Scripts/python -m app.cli fingerprint-account
# Enter the full Moomoo acc_id at the hidden prompt; only the SHA-256 fingerprint is printed.

.venv/Scripts/python -m app.cli approve-first-order \
  --proposal-id <proposal-id> --strategy-version spy-directional
```

Set `COMPETITION_ACCOUNT_MASKED_ID`, `COMPETITION_ACCOUNT_FINGERPRINT` and `COMPETITION_ACCOUNT_MARKET_ID` locally. The account lock fails closed if they are missing.

## Known limitations and pending milestones

1. **No broker-confirmed order or fill.** The separately approved supervised diagnostic paper BUY/SELL has not been completed. Mock, fixture and preview results are not broker evidence, and paper-account performance is intentionally shown as unavailable.
2. **SH/UPRO/SPXU are research-only.** The production allowlist remains `SPY`/`QQQ`/`IWM`; SH is rejected at `R002`, and UPRO/SPXU additionally require the opt-in `R015` leverage gate. No leverage is enabled.
3. **Execution scope is not account-exclusive.** The separate execution token holds `quote:read trade:read trade:write`, but Moomoo documentation does not confirm that an `accid:` binding narrows `trade:write` to the competition account. It is treated as potentially account-wide.
4. **No demonstrated forward edge.** The `spy-directional` rules are frozen and unoptimised. The historical sanity check underperformed SPY buy-and-hold; it is not alpha evidence.
5. **Python cannot call the cloud Moomoo MCP.** Vault credentials are injection-only, so authenticated reads and previews use the local OAuth REST client. Cloud agents remain research/audit-only.
6. **Scheduling is local.** Windows Task Scheduler runs the read-only workflow; Qoder Cloud cron cannot access the local DPAPI token, repository or ledger.

## Owner setup

See [`docs/integrations.md`](docs/integrations.md). The owner must personally register/authorise Qoder and Moomoo, verify the competition account, and supply local secrets through environment/secret stores—not chat or GitHub.

## License and attribution

This project does not vendor external repositories. The research references below were inspected as separate, pinned clones and have been moved outside the repository (archive: `../mootrade-reference-archive/`). Their licences and revisions are recorded here for attribution:

| Reference | Pinned revision | Licence | Use |
|---|---|---|---|
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | `5c553b5222044f6a5527bd377b4104c50ee0ad28` | MIT | Studied risk-policy and ledger ideas; no code imported |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | `9fa1196fffbcfd9de5146d2dd2869df84ab99838` | Apache-2.0 | Architecture reference only; no code imported |
| [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | `a8d815d17ec054a34dbdfc7ce8d1d9972566b709` | MIT | Separate pinned research study; not a dependency |
| [MoomooOpen/moomoo-agent-plugin](https://github.com/MoomooOpen/moomoo-agent-plugin) | `0b28d3c23f08702fd0afae9d3a639ff0fb21290b` | MIT | Reference for Moomoo MCP tool names; the app connects to `https://mcp.moomoo.com/mcp` directly |

The dashboard UI adapts the MIT-licensed Shadcn Fintech template; attribution is in [`frontend/ATTRIBUTION.md`](frontend/ATTRIBUTION.md).
