# MooTrade

**A Qoder-native autonomous paper-trading control centre for the 2026 Moomoo × Qoder AI Trading Agent Challenge.**

> An AI trading team that doesn't just know when to trade. It knows when to stop.

**Status:** local mock safety core, deterministic research/dry-run pipeline, a **verified local read-only Moomoo REST transport** and a **six-section read-only MooTrade dashboard** backed by typed FastAPI endpoints. A fresh read-only preflight against the competition account passed quote, session and account freshness checks and was rejected only by policy controls (`R010` writes disabled, `R014` first-order approval missing); no order endpoint was contacted. The dashboard has no order-capable action. **Verified 17 November 2026:** the competition paper account `****0101` (`account_type=2`, `market_id=100`, exact title, fingerprint match) reports 100,000 USD cash/equity with zero positions or orders through both the earlier vault-attached cloud MCP read and the new local OAuth 2.1 + PKCE REST client. A genuine current-market read-only run during the US regular session (`AFTERNOON`) produced `NO_TRADE` because the broad-market regime filter was negative, and one local scheduled execution completed read-only with `NO_TRADE`; no order was submitted or approved. The 17 November timer was missed because the host was in Modern Standby. A Task Scheduler task with wake/start-when-available, two UTC triggers for both ET DST offsets, catch-up and durable idempotent state now runs the schedule unattended. A genuine timer-triggered catch-up at `09:10:52 SGT` on 18 November completed `NO_TRADE` (Qoder run `qoder-83bc0a47-e238-4672-a5cc-42e8080180ce`), and the one-time validation trigger was then removed. A Moomoo technical-signal audit on 18 November found candlestick/polarity data are snapshot-only and provider backtest windows are undisclosed; a pre-registered oversold-reversal candidate was rejected, and `momentum-v1` remains unchanged with `NO_TRADE`. See [`docs/strategy-and-risk.md`](docs/strategy-and-risk.md). The local read token is DPAPI-encrypted outside the repository; the REST client allows GET account reads plus two documented POST-for-read quote/market-state endpoints and has no order path. The separate execution OAuth client is now authorized with `quote:read trade:read trade:write` plus an account binding, in a separate DPAPI token store; the read-only token still has no `trade:write`. A read-only `moomoo-execution-check` verified the exact competition account and reported `order_endpoint_contacted=false`; account-exclusive write scope remains unverified. A documented simulated-order transport and paper-broker facade are composed by an operator-only supervised CLI boundary, but writes require both explicit CLI flags, an exact durable approval and every preflight check; mock tests cover the complete path, and no order endpoint has been contacted. Qoder Cloud Agent v4 retains platform-level `always_deny` for all ten order-writing MCP tools, and the Qoder research workflow remains read-only. Raw Moomoo results contain full account ids, so cloud session logs must not be exported. `ORDER_WRITES_ENABLED=false`. See [`docs/integrations.md`](docs/integrations.md).

## What judges will see

A desktop-first web dashboard showing (1) paper account equity, cash and exposure; (2) Qoder Cloud Agent runs; (3) research evidence and trade proposals; (4) deterministic risk decisions; (5) broker-confirmed orders/fills; and (6) portfolio reconciliation, incidents and performance.

The defining demo is **one traceable decision from market data through Qoder agents to a broker-confirmed paper outcome**, plus a safe test showing a rejected oversized order never reaches the broker.

## Read these in order

1. [`plan.md`](plan.md) — goals, rubric, scope and timeline.
2. [`docs/architecture.md`](docs/architecture.md) — trust boundaries, data flow and services.
3. [`docs/integrations.md`](docs/integrations.md) — what the owner must set up, what is verified, and what remains blocked.
4. [`docs/strategy-and-risk.md`](docs/strategy-and-risk.md) — exact policies and required tests.
5. [`docs/dashboard.md`](docs/dashboard.md) — six sections, read-only API, provenance and states.
6. [`docs/build-checklist.md`](docs/build-checklist.md) — sequenced deliverables and acceptance gates.
7. [`docs/judge-demo.md`](docs/judge-demo.md) — evidence and submission rehearsal.
8. [`AGENTS.md`](AGENTS.md) — constraints for the coding agent.

## Tentative stack

- Qoder Cloud Agents: orchestrated researcher, strategy, risk-review and execution/reporting workflows.
- Moomoo **competition-specific** MCP connection: quotes, account state and authorised paper orders only.
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

## Research pipeline and dry-run report

`backend/app/research/` implements two frozen strategies over daily bars and timestamped news, with no look-ahead:

- `momentum-v1`: SPY must close above its 20-session SMA; candidates need a close above their own 20-session SMA and a positive 5-session return; the highest 5-session return is selected, with an alphabetical tie-break.
- `news-catalyst-v1`: the same price rules plus at least one relevant headline in the prior 72 hours and a positive recency-weighted keyword sentiment score.

The pipeline screens candidates with explicit reasons to buy or skip, builds a `TradeProposal` with source evidence IDs, and calls the existing `RiskGate.evaluate` directly in dry-run. It never calls `TradingService.execute`, the mock broker or a Moomoo order tool.

**Sample report:** [`evidence/sample-reports/decision-report-2026-11-17.md`](evidence/sample-reports/decision-report-2026-11-17.md). The last completed session (2026-11-16) is `NO TRADE` for both strategies because SPY closed below its 20-session SMA. The report also contains hypothetical approved proposals (IWM 17 shares on 2026-10-28; QQQ 6 shares on 2026-10-08), fail-closed rejections for stale quotes (`R007`), oversized sizing (`R004`), disabled writes (`R010`) and missing first-order approval (`R014`), plus a historical signal-quality study.

That historical study is **not** the return of the paper account and does not predict future returns. Over 2025-06-27 to 2026-11-16, `momentum-v1` returned -0.41% versus +19.83% for SPY buy-and-hold; over the shorter news window (2026-02-10 to 2026-11-16), `momentum-v1` returned -3.77%, `news-catalyst-v1` +1.56%, SPY +6.23% and QQQ +7.34%. Both strategies were first drafts; parameters were frozen before evaluation and no search was performed.

Applying the deployable limits to the same frozen rules changes the result to `+0.09%` total return, `1.22%` maximum drawdown and `6.62%` average exposure, versus `+2.07%` for a 10% SPY holding, `+1.37%` for a 6.62%-entry SPY holding and `+0.43%` for SPY on the strategy's exact entry/exit sessions. The improvement from the prior `-0.41%` is a sizing effect, not alpha; the strategy still loses to SPY on matched dates. Evidence: [`evidence/research/momentum-deployable-2026-11-18/report.md`](evidence/research/momentum-deployable-2026-11-18/report.md). A separate `volume-confirmed-relative-strength-v1` stock-selection hypothesis is pre-registered but **not evaluated or deployed**; it uses only reconstructable daily OHLCV and the RiskGate allowlist is unchanged. Protocol: [`evidence/research/stock-selection-prereg-2026-11-18/protocol.json`](evidence/research/stock-selection-prereg-2026-11-18/protocol.json). See [`docs/strategy-and-risk.md`](docs/strategy-and-risk.md).

`etf-trend-baseline-v1` is a separate low-turnover comparator: hold SPY at the 10% policy cap only while its completed month-end close is above its 200-session SMA, execute at the next open. Over the post-warmup window (2026-04-01 to 2026-11-16), it returned +0.26% with one entry and 0.63% maximum drawdown, versus +1.31% for a matched 10% SPY holding and +13.14% for fully invested SPY. The short sample, monthly lag and entry-time-only cap are documented limitations; it is not registered as an executable strategy. Evidence: [`evidence/research/etf-trend-baseline-2026-11-17/report.md`](evidence/research/etf-trend-baseline-2026-11-17/report.md).

Reproduce from the repository root (the account fingerprint is read from the local environment and never printed):

```bash
.venv/Scripts/python -m app.research.demo \
  --bars backend/tests/fixtures/moomoo_daily_bars_2026-11-16.json \
  --news backend/tests/fixtures/moomoo_news_2026-11-17.json \
  --out evidence/sample-reports/decision-report-2026-11-17.md
```

Market bars are a committed normalized fixture from a real read-only Moomoo `quote_cur_kline` call (370 daily bars per ETF, 2025-05-29 to 2026-11-16, forward-adjusted; source timestamp 2026-11-17T06:30:00Z). News metadata comes from read-only `news_search` (152 headlines with provider publish times). Neither fixture contains credentials or account identifiers.

Reproduce the ETF baseline study:

```bash
.venv/Scripts/python backend/scripts/etf_baseline_study.py
```

Reproduce the deployable-limit study:

```bash
cd backend && ../.venv/Scripts/python -m scripts.momentum_deployable_study
```

## Qoder read-only orchestration

A genuine three-agent Cloud Agent run completed for run `qoder-5abed69d-8fbc-4342-a51f-e46814f3941c`:

- coordinator `sess_00vrjkuvor0n5z2xowpc`
- researcher `sess_00vrjkz4rxkaolrwifgl`
- auditor `sess_00vrjl9k6r08wt8i5u0z`

The researcher called the fixed `research_market` custom tool; the auditor independently confirmed `NO_TRADE`; the coordinator closed the report. Sessions used no Moomoo MCP servers, no Vault, no repository resources and no order tools. The deterministic snapshot was historical evidence only: SPY 739.95 was below its 20-session SMA 757.695, so no candidate was eligible. Sanitized artifacts are in [`evidence/qoder/`](evidence/qoder/); raw cloud session events are not exported. The local runner enforces strict tool inputs, pinned run state and one tool result per call, and does not retry ambiguous delivery.

Qoder Cloud Agents remain the research and audit layer, not the broker transport. Authenticated competition-account reads now use the separate local REST client; no agent has an order path. The execution architecture, remaining blockers and acceptance tests are recorded in [`docs/integrations.md`](docs/integrations.md).

## Read-only dashboard and API

The dashboard is an adapted copy of the Shadcn Fintech template (MIT, attribution in [`frontend/ATTRIBUTION.md`](frontend/ATTRIBUTION.md)) with six desktop-first sections: Overview, AI Agent Activity, Portfolio & Orders, Risk Centre, Performance Analytics and Audit Log. It shows only backend-computed values; the browser never receives OAuth credentials, account fingerprints or PATs. A PAPER banner and per-block provenance labels separate live broker reads, local ledger/controls, the recorded historical Qoder run and historical strategy curves. Paper-account performance is explicitly unavailable because there are no fills.

The FastAPI app exposes seven GET-only routes (`/api/v1/health`, `/overview`, `/portfolio`, `/risk`, `/agents`, `/analytics`, `/audit`) plus OpenAPI docs. Non-GET requests return 405, the server refuses to start with writes enabled, and access requires either an optional `MOOTRADE_DASHBOARD_TOKEN` bearer token or a loopback client. The Next.js server proxy allowlists the same six dashboard paths. Details: [`docs/dashboard.md`](docs/dashboard.md).

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

On macOS/Linux, use `.venv/bin/python` instead. **Verified on 18 November 2026 with Python 3.14.5: 299 tests passed**, including REST OAuth, execution-scope validation, registration-only status rejection, REST read transport, disabled order-transport success/partial/rejection/timeout/duplicate/`UNKNOWN` mocks, supervised CLI missing-approval/kill-switch/wrong-account/closed-market/ambiguous guards, execution preflight/correlation/reconciliation, CLI, Qoder runner/tool, research/dry-run, ETF baseline, scheduler catch-up/idempotency/interruption recovery, clock-skew handling and dashboard API tests. The dashboard also passed 10 formatting regression tests, TypeScript typecheck, ESLint and `next build`. The authenticated REST account reads are real provider evidence; the remaining tests are unit, fixture and mock results. No fill or order result has been observed.

### First-order approval (operator action, never submits an order)

```bash
.venv/Scripts/python -m app.cli fingerprint-account
# Enter the full Moomoo acc_id at the hidden prompt; only the SHA-256 fingerprint is printed.

.venv/Scripts/python -m app.cli approve-first-order \
  --proposal-id <proposal-id> --strategy-version momentum-v1
```

Set `COMPETITION_ACCOUNT_MASKED_ID`, `COMPETITION_ACCOUNT_FINGERPRINT` and `COMPETITION_ACCOUNT_MARKET_ID` locally. The account lock fails closed if they are missing.

## Owner setup

See [`docs/integrations.md`](docs/integrations.md). The owner must personally register/authorise Qoder and Moomoo, verify the competition account, and supply local secrets through environment/secret stores—not chat or GitHub.

## License and attribution

This is a new project. External GitHub repositories are **references**, not automatically imported dependencies. Before reusing code or UI assets, inspect licence, provenance, current dependencies and competition restrictions; record citations and credits in an attribution file before submission.
