# MooTrade

**A Qoder-native paper-trading control centre with supervised approval for every order, for the 2026 Moomoo × Qoder AI Trading Agent Challenge.**

> An AI trading team that doesn't just know when to trade. It knows when to stop.

**Status:** local mock safety core, a **verified local read-only Moomoo REST transport**, a **six-page read-only MooTrade dashboard**, and one active S&P 500 directional research strategy, **`spy-directional`**, using **risk-v3 only** (SPY bullish / SH bearish / CASH, 10%–40% allocations, 1x only, one directional position). Deterministic code evaluates completed SPY daily bars and computes tiered signed exposure. The current mandate is **supervised approval for EVERY BUY and SELL**, bound to the exact proposal and client order key. `TRADING_MODE=SUPERVISED_PAPER` and `ORDER_WRITES_ENABLED=false` remain unchanged. UPRO/SPXU were removed from the universe on 20 November 2026 (risk-v3 cutover) and are rejected by default-deny symbol validation; their historical records are preserved. The stale 576-SH BUY approval was superseded in the append-only ledger on 20 November. Read-only SPY/SH MARKET capacity was verified on 19 November (112/2,476 cash-buy shares), not broker acceptance. No new activation, permission or order is implied. The 18 November risk-v1 (16:03Z) and pre-simplification risk-v2 (23:58Z: SPY/UPRO/SH/SPXU, 20% floor / 150% ceiling / 3x / 2% drawdown) activation pins remain append-only **HISTORICAL** records, not current unattended authority; risk-v1 and pre-simplification risk-v2 cannot be reactivated. Autonomous trading requires separate explicit approval, never automatic restoration. QQQ is historical diagnostic reconciliation only; its separately approved BUY/SELL both filled and reconciled on 18 November. No strategy order has been submitted.

The competition paper account `****0101` (`account_type=2`, `market_id=100`, title and fingerprint match) was verified at 100,000 USD cash/equity with zero positions or orders through the local OAuth 2.1 + PKCE REST client. Read and execution tokens remain DPAPI-encrypted outside the repository; the read token has no `trade:write`. The documented simulated-order transport and supervised CLI remain disabled by default and require two explicit flags, a durable approval and every preflight check; the only submissions to date are the two 18 November supervised diagnostic orders, each behind its own owner approval, both reconciled. `ORDER_WRITES_ENABLED=false` and no strategy order exists. Qoder Cloud Agent v4 keeps `always_deny` on all order-writing MCP tools. A genuine 18 November three-agent run under `spy-directional` produced a policy-rejected SH proposal under the retired sizing; it is **HISTORICAL** evidence, not the latest risk-v2 decision or a new cloud run. See [`docs/strategy-and-risk.md`](docs/strategy-and-risk.md) and [`docs/integrations.md`](docs/integrations.md).

## What judges will see

A desktop-first web dashboard showing (1) paper account equity, cash and exposure; (2) Qoder Cloud Agent runs; (3) research evidence and proposals; (4) deterministic risk decisions; (5) broker order and fill state from reconciliation; and (6) portfolio reconciliation, incidents and performance provenance.

The target demo is **one traceable strategy decision from market data through Qoder agents to a broker-confirmed paper outcome**, plus a safe rejection test. Broker-confirmed diagnostic QQQ BUY `3115842` and SELL `3115920` both filled and reconciled on 18 November; they are not strategy performance, and no SPY/SH fill is claimed.

## Read these in order

1. [`docs/architecture.md`](docs/architecture.md) — trust boundaries, data flow and services.
2. [`docs/strategy-and-risk.md`](docs/strategy-and-risk.md) — the active `spy-directional` rules, RiskGate policy and required tests.
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

No live-money trading or secrets in source control. Every supervised order requires exact-proposal/key owner approval; autonomous execution requires separate explicit authorisation and is not currently permitted.

## Working order

**Integration discovery → read-only account sync → policy and audit ledger → one controlled paper order → Qoder scheduling → dashboard → evidence → deck.**

The dashboard must never show fictional account values as real. All mock data is visibly labelled and isolated from the live competition paper-account view.

## Local mock core

The backend contains an exact competition-account lock (masked id + SHA-256 fingerprint, simulated source only), typed contracts, a deterministic **risk-v3-only** gate, paper-only mock broker, append-only SQLite ledger, durable idempotency, persistent kill switch, per-order owner approval and an enforced state machine. Active research targets are tiered from 10% to 40% signed-exposure magnitude, or CASH. The 40% signed-effective ceiling and ±5 percentage-point declared-target tolerance are enforced; only the supervised path skips the 10% floor. RiskGate permits one position (matching the strategy), keeps a US$5 cash buffer and a 2% daily-drawdown brake, and requires quotes ≤300s and account snapshots ≤60s. Execution scope is SPY/SH only with a 1x leverage maximum; this grants no order permission. Mock coverage includes rejection, acknowledgement, full/partial fills, ambiguous timeouts and reconciliation; current verification results are recorded in `docs/evidence.md`.

`backend/app/broker/moomoo_readonly.py` adds a read-only adapter over an injected MCP tool caller. It can invoke only `sim_trade_account_list`, `sim_trade_cash_info`, `sim_trade_position_list` and `sim_trade_history_order_list`; it rejects every other tool name before the caller, including all ten order-writing tools. It resolves the exact competition account through the existing lock, converts cash/positions/orders into `AccountSnapshot`, persists the daily equity baseline in SQLite, ignores margin buying power (`max_power_long`) for cash-only sizing, and has no order-submission method. The earlier Python-to-cloud-MCP bridge remains unavailable because vault secrets are injection-only, so that adapter is still fixture-tested. `moomoo_auth.py` and `moomoo_rest.py` now provide a separate local OAuth 2.1 + PKCE read path with DPAPI token storage and GET-only allowlisted sim-trade endpoints, plus two documented POST-for-read quote endpoints; it verified the same competition account and state against the real provider. `moomoo_quotes.py` adds execution-time quote freshness, symbol and regular-session checks. `moomoo_orders.py` adds a documented simulated-order payload builder, bounded `text` correlation tag, strict status mapping, `UNKNOWN` reconciliation from today's orders/history/positions, and a guarded `MoomooOrderTransport` that can POST only to `/api/v1.0/sim-trade/{acc_id}/orders`. The transport is disabled by default, never retries, and converts any unclear response into `UNKNOWN`; `MoomooPaperBroker` composes it with the read adapter and existing controls. The supervised CLI scopes writes only to an explicitly approved invocation; the QQQ diagnostic BUY/SELL are the only provider-observed submissions. Runtime writes remain disabled, and the REST read client still explicitly rejects order submission.

### Local read-only Moomoo REST

```bash
.venv/Scripts/python -m app.cli moomoo-login
.venv/Scripts/python -m app.cli moomoo-auth-status
.venv/Scripts/python -m app.cli moomoo-read
.venv/Scripts/python -m app.cli moomoo-preview-order --symbol <symbol> --action <BUY-or-SELL> --quantity <quantity> --proposal-id <proposal-id>
.venv/Scripts/python -m app.cli moomoo-execution-login
.venv/Scripts/python -m app.cli moomoo-execution-status
.venv/Scripts/python -m app.cli moomoo-execution-check
```

Complete browser consent with read permissions only for `moomoo-login`; do not grant `trade:write` there. `moomoo-preview-order` performs a fresh quote/session read with the read token, evaluates the deterministic gate and prints the documented payload, risk reasons and safety checks; `submission_performed` is always `false`. `moomoo-execution-login` is a separate client and token file for a supervised order; it requests `quote:read trade:read trade:write` and warns that account-exclusive write scope is unverified. `moomoo-execution-check` uses read-only calls and confirms the account but never contacts an order endpoint. `moomoo-read` prints sanitized `PAPER` JSON with account identity, cash, positions, open orders, paginated history, timestamps and reconciliation. The sim-account token may show `quote:read` plus an `accid:` binding instead of a literal `trade:read`; the validator accepts that read-equivalent binding and rejects any `trade:write` grant. Both tokens are stored in DPAPI-encrypted files outside the repository.

`moomoo-supervised-preview` evaluates without submitting and reports per-rule states plus current/post-order signed-effective exposure. The prepared `--proposal-file` addition to preview/execute preserves the exact research timestamps, evidence and target; all existing required flags must match the file. `moomoo-supervised-execute` requires the current `SUPERVISED_PAPER` mode, `--enable-order-writes`, exact `--confirm-client-order-key`, durable owner approval for EVERY BUY/SELL proposal/key, fresh quote/account, regular session, reconciliation, clean kill switch and every applicable risk-v2 rule. It submits at most once, never retries ambiguity and reconciles read-only. `moomoo-supervised-reconcile` only reads. The only submitted orders remain the historical QQQ diagnostic round trip (`3115842`/`3115920`, both filled and reconciled).

`moomoo-auto-paper-status` is read-only. Old activation pins and dormant AUTO_PAPER machinery are **HISTORICAL**, not permission to trade unattended; do not reactivate risk-v1 or restore autonomy after acceptance orders. Separate explicit owner approval is required for any future autonomous scope. The operator can stop new submissions with `moomoo-kill-switch --engage --confirm-engage` (confirmation required; `--release --confirm-release` releases the switch only, not order-approval requirements).

## Research pipeline: `spy-directional`

`backend/app/research/` implements one active strategy over completed daily bars, with no look-ahead:

1. Each completed session computes SPY's 10-session return, 50-session SMA and 20-session annualised realised volatility from provider bars.
2. **Direction:** sign of the 10-session return (`>= +1.5%` BULLISH, `<= -1.5%` BEARISH, otherwise NEUTRAL/CASH). Annualised volatility above `40%` forces CASH.
3. **Target exposure (risk-v3 only):** analyse → direction → strength/risk → signed S&P 500 exposure fraction → ETF → cash allocation and whole shares. Absolute-return tiers: `<1.5%` → `0%`; `1.5–3%` → `10%`; `3–5%` → `25%` (trend-confirmed `40%`); `5–8%` → `40%`; `>= 8%` → `40%` (capped). Annualised volatility above `40%` forces CASH.
4. **ETF selection:** SPY (bullish) / SH (bearish), 1x only, with cash allocation `equity × |target|`. UPRO/SPXU are outside the risk-v3 universe. Inverse exposure uses BUY orders, never short-selling.
5. **State:** a matching holding produces HOLD unless a resize rule applies; a neutral or non-matching target produces CASH or SELL. Reversal entry is considered only by a later run after broker-confirmed flat state. One directional position at a time.
6. **Adjustments:** tier moves resize only when the share delta is `>= 1` share and `>= 5%` relative; direction flips SELL first. Every BUY/SELL, including exits and resizes, still requires exact-proposal owner approval. No repeated intraday BUYs from the same daily signal.
7. **RiskGate is final on eligibility:** risk-v3 only, 10% research floor (skipped only in the supervised path), 40% signed-effective ceiling, ±5pp target tolerance and the 40% competition single-security concentration cap (`R019`). Execution scope is SPY/SH only, 1x maximum. A `40%` exposure can lose about `0.8%` of equity on a `2%` adverse index move; the 2% drawdown brake does not cap losses or eliminate gap risk.

The exact policy, state transitions and limitations are in [`docs/strategy-and-risk.md`](docs/strategy-and-risk.md).

**Latest research, not an order:** completed 18 November bars show SPY `730.2`, 10-session return `-4.7743248%`, SMA50 `762.2828597323`, volatility `22.8820254%` → BEARISH. Under the pre-simplification risk-v2 tiers (HISTORICAL) this mapped to an SH target of **−60%**; the genuine three-agent run `qoder-4e73fe0c-6d70-4722-84ac-aaf0f9dc1b3e` proposed BUY 1,764 SH. Its read-only gate rejected R010/R014; the 15:02Z supervised preview rejected only missing exact-order approval with hypothetical writes enabled. Actual writes stayed disabled; see `docs/evidence.md`. Under risk-v3 the same measurements map to the `3–5%` MODERATE band: −25% base, −40% trend-confirmed (close below SMA50). The current decision is regenerated by the standard workflow before any proposal. Read-only SPY/SH MARKET capacity was verified on 19 November (112/2,476 cash-buy shares).

**HISTORICAL performance, not v2 returns:** the frozen 12 August 2025–17 November 2026 sanity run used retired 5% sizing and returned `-0.40%`, `0.42%` annualised volatility, `0.59%` maximum drawdown, `41%` of sessions exposed, 35 trades and a `41.18%` win rate, versus SPY buy-and-hold at `+15.47%`. These unchanged results are neither alpha nor paper-account evidence and cannot justify reactivating risk-v1.

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

The workflow uses exactly three Qoder Cloud Agents: a **coordinator** that validates the run boundary and closes the report, a **researcher** that calls `research_market`, and an independent **risk auditor** that challenges the evidence and calls `evaluate_proposal` only when a proposal exists. The coordinator has no tools; none of the agents has an order path. On 18 November 2026 the deployed researcher agent was updated to version 4, replacing the retired `directional-event-v2` enum with `spy-directional`. **HISTORICAL run:** the genuine current-market three-agent run `qoder-328aefff-7dde-4a98-ac76-99b3e0e33728` then completed under the retired sizing, not the latest v2 −60% target:

- coordinator `sess_00vuffkjlafwgresy62p`
- researcher `sess_00vuffpgw47pdzx2s53d`
- auditor `sess_00vufg56d34sgybrbybv`

The researcher called `research_market` once on real Moomoo bars through 17 November 2026. Its sanitized artifact records a BEARISH signal at `732.44`, a 10-session return of `-2.90%`, SMA50 `762.89`, volatility `23.06%`, deterministic selection of SH at 1x and a 147-share BUY proposal. The auditor called `evaluate_proposal` once; the real `RiskGate` rejected it for `R002` (SH outside the production allowlist), stale post-close quote, non-regular session, disabled writes (`R010`) and missing first-order approval (`R014`). The coordinator closed the run with outcome `POLICY_REJECTED`; no order was created or filled. Evidence: [`evidence/qoder/qoder-328aefff-7dde-4a98-ac76-99b3e0e33728.md`](evidence/qoder/qoder-328aefff-7dde-4a98-ac76-99b3e0e33728.md).

The earlier event-strategy runs are retained under `evidence/qoder/` as historical execution evidence, not as current `spy-directional` results. The local runner enforces strict tool inputs, pinned run state and one tool result per call, and does not retry ambiguous delivery.

Qoder Cloud Agents remain the research and audit layer, not the broker transport. Authenticated competition-account reads use the separate local REST client; no agent has an order path. The execution architecture, remaining blockers and acceptance tests are recorded in [`docs/integrations.md`](docs/integrations.md).

## Read-only dashboard and API

The dashboard has six desktop-first pages: Overview (`/dashboard`), AI Agent Activity (`/agents`), Portfolio & Orders (`/portfolio`), Risk Centre (`/risk`), Performance Analytics (`/analytics`) and Audit Log (`/audit`). It shows only backend-computed values; the browser never receives OAuth credentials, account fingerprints or PATs. PAPER mode is displayed by the persistent sidebar account card, which reports the actual recorded trading mode (`PAPER · READ ONLY` / `SUPERVISED` / `AUTO_PAPER`) and effective order-write state, alongside per-block provenance labels that separate live broker reads, local ledger/controls, the recorded historical Qoder run and historical strategy curves. Strategy paper-account performance is unavailable: the only fills are the historical diagnostic QQQ BUY/SELL, not strategy results; historical curves are not risk-v2 returns.

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

On macOS/Linux, use `.venv/bin/python` instead. **HISTORICAL verification record:** 401 backend tests passed on 19 November 2026 with Python 3.14.5 before this mandate change; the dashboard also passed 17 formatting tests, TypeScript typecheck and ESLint. That record includes retired dual-policy coverage and must not be read as validation of the new v2-only/per-order-approval changes. Current v2-only verification results are recorded separately in `docs/evidence.md`. Unit, fixture and mock results are not provider evidence. The only broker-confirmed fills are the two 18 November supervised diagnostic QQQ orders.

### Approval for EVERY supervised BUY/SELL (never submits)

The historical CLI name `approve-first-order` is retained, but is used for **each exact proposal/key**, including after prior fills. Owner approval is durable; the separate risk decision expires after 30 seconds and must be refreshed on expiry or account-state change. Use `--proposal-file` for the exact research handoff described in [`docs/operations.md`](docs/operations.md); do not repeat diagnostics or create replacement keys.

```bash
.venv/Scripts/python -m app.cli fingerprint-account
# Enter the full Moomoo acc_id at the hidden prompt; only the SHA-256 fingerprint is printed.

.venv/Scripts/python -m app.cli approve-first-order \
  --proposal-id <proposal-id> --strategy-version spy-directional
```

Set `COMPETITION_ACCOUNT_MASKED_ID`, `COMPETITION_ACCOUNT_FINGERPRINT` and `COMPETITION_ACCOUNT_MARKET_ID` locally. The account lock fails closed if they are missing.

## Known limitations and pending milestones

1. **Broker-confirmed diagnostic only.** The separately approved supervised QQQ diagnostic BUY (broker order `3115842`, filled at 661.72) and SELL (`3115920`, filled at 654.73) are complete and reconciled on 18 November 2026. No strategy trade has been authorised. Mock, fixture and preview results are not broker evidence, and paper-account performance is intentionally shown as unavailable.
2. **SPY/SH-only execution scope is not broker acceptance.** Read-only SPY/SH MARKET cash-buy capacity was verified on 19 November at 112/2,476 shares; no order acceptance or fill is claimed. UPRO/SPXU were removed from the risk-v3 universe on 20 November and are rejected by default-deny symbol validation; their read-only quotes/books/session access remain HISTORICAL evidence. The historical four-symbol pin does not expand current permission. Every supervised BUY/SELL needs exact-proposal/key approval; acceptance never automatically restores autonomy. QQQ is historical diagnostic reconciliation only.
3. **Account-exclusive execution scope is unverified.** The separate execution token holds `quote:read trade:read trade:write`, but Moomoo documentation does not confirm that an `accid:` binding narrows `trade:write` to the competition account. It is treated as potentially account-wide.
4. **No demonstrated forward edge.** The `spy-directional` rules are frozen and unoptimised. The historical sanity check underperformed SPY buy-and-hold; it is not alpha evidence.
5. **Python cannot call the cloud Moomoo MCP.** Vault credentials are injection-only, so authenticated reads and previews use the local OAuth REST client. Cloud agents remain research/audit-only.
6. **Scheduling is local.** Windows Task Scheduler runs the read-only workflow; Qoder Cloud cron cannot access the local DPAPI token, repository or ledger.

## Owner setup

See [`docs/integrations.md`](docs/integrations.md). The owner must personally register/authorise Qoder and Moomoo, verify the competition account, and supply local secrets through environment/secret stores—not chat or GitHub.

## License and attribution

This repository is licensed under the MIT License (see [`LICENSE`](LICENSE)).
