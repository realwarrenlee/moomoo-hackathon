# MooTrade — Moomoo × Qoder AI Trading Agent Challenge

**Project plan and implementation specification**  
**Version:** 18 November 2026  
**Development and paper-trading window:** 17–28 November 2026  
**Submission deadline:** 30 November 2026, 23:59 SGT  
**Finalist presentations:** 8 December 2026  
**Status:** Implemented read-only research, agents and dashboard; supervised paper execution is built but disabled and the first paper order is still pending.

---

## 1. Executive summary

**MooTrade is a Qoder-native autonomous paper-trading control centre.** It uses three Qoder Cloud Agents — coordinator, researcher and independent risk auditor — to research the market and review the deterministic decision, while deterministic Python enforces non-negotiable risk limits. Only a separately supervised, operator-only command can submit to the competition's Moomoo paper account through the local OAuth REST adapter; it is disabled by default. A six-page web dashboard makes decisions, rejections, account state and provenance visible and auditable.

**Pitch:** *An AI trading team that doesn't just know when to trade. It knows when to stop.*

The objective is **not** to maximise raw trading profit over a short period. The objective is to submit a convincingly autonomous, reliable, reusable trading-agent system that scores well under the organisers' rubric. The strategy must be credible and measurable, and trading results must be genuine, but risk-adjusted returns represent only 25% of the stated scoring.

### Judging criteria and product response

| Criterion | Weight | How MooTrade demonstrates it |
|---|---:|---|
| Qoder & Qoder Cloud Agent usage | **30%** | Qoder-hosted specialised agents, automated runs, MCP tool calls, structured handoffs, reusable skills, execution history and dashboard |
| Strategy & risk design | **30%** | Explicit trading hypothesis, precise entry/exit criteria, independent pre-trade policy gate, drawdown handling, kill switch and failure tests |
| Reusability & documentation | **15%** | Clean repository, installation guide, configuration templates, unit tests, runbooks, logged decisions, Qoder-generated presentation |
| Risk-adjusted return | **25%** | Verifiable Moomoo paper fills, equity and drawdown history, benchmark and exposure comparisons; no invented trades or results |

**Guiding principle:** Build the smallest complete *end-to-end* product first. Add visual polish, research sophistication and optional features only after safe paper execution, state reconciliation and logging work.

### Strategy decision — 18 November 2026

The original momentum and news-catalyst hypotheses did not produce a defensible edge and are retired from the active product. The active strategy is **`spy-directional`**: one deterministic daily S&P 500 direction rule over completed SPY bars, with exactly four candidate ETFs (SPY `+1x`, UPRO `+3x`, SH `-1x`, SPXU `-3x`) or CASH. Bullish/bearish requires a `±1.5%` 10-session return with price on the matching side of the 50-session SMA; 20-session annualised volatility above `40%` forces CASH. Strong labels require `±3.0%` and volatility at or below `30%`, and select the 3x fund only when leverage is separately enabled. Target size is `5%` effective exposure, with HOLD, SELL/CASH, confirmed-fill reversal and one directional position at a time. The full specification, state transitions, leverage gate, evidence limitations and acceptance/rejection criteria are in [`docs/strategy-and-risk.md`](docs/strategy-and-risk.md). `momentum-v1`, `news-catalyst-v1`, `directional-event-v2`, the stock-selection pre-registration, the Moomoo oversold-reversal candidate and the research-only ETF trend comparator are retained only as historical evidence.

The pivot does not change the execution boundary: no agent receives order authority and `ORDER_WRITES_ENABLED=false`. On 18 November 2026 the research and supervised-execution gates were given the four-symbol universe with per-symbol leverage metadata, so SPY and SH (1x inverse, BUY only) are eligible while UPRO/SPXU remain disabled by `R015` until separately approved; QQQ is preserved for historical diagnostic reconciliation only. The first supervised diagnostic paper BUY/SELL test was completed and reconciled on 18 November 2026 (`evidence/execution/diagnostic-roundtrip-2026-11-18.json`).

---

## 2. End product: what the judges will see

A working **web-based trading operations dashboard** connected to the actual competition paper account and Qoder agent activity.

### Primary screens

1. **Overview** (`/dashboard`) — Account equity, cash, market tape, open positions, latest Qoder run, local controls, recent ledger events and paper-mode/writes-disabled status.
2. **AI Agent Activity** (`/agents`) — Genuine Qoder sessions and role summaries, the SPY signal, four candidate ETFs, target/current position, risk verdict and evidence timestamps.
3. **Portfolio & Orders** (`/portfolio`) — Broker-reported holdings, open orders, today's orders, order history and reconciliation status.
4. **Risk Centre** (`/risk`) — Locked state, limits, current inputs, rule catalogue and the recorded real preflight.
5. **Performance Analytics** (`/analytics`) — Historical normalised research curves, metrics and explicit limitations; never presented as paper-account performance.
6. **Audit Log** (`/audit`) — Append-only ledger timeline with filters.

### Must-have demonstration

The judges must be able to see a **real end-to-end agent decision** recorded with provenance:

`Qoder market research → deterministic spy-directional proposal → independent agent review → deterministic RiskGate → supervised paper-broker submission → verified broker response/fill → ledger reconciliation → dashboard and report`

The final two steps remain pending: no supervised paper order has been submitted, so there is no broker-confirmed order or fill yet.

Additionally, demonstrate a deliberately **oversized order being rejected** without reaching the broker. This is a controlled test, not a fabricated trading record.

### Out of scope for this challenge

- Trading live capital or handling live brokerage credentials.
- Claiming that short paper-trading returns prove durable alpha.
- Building proprietary predictive ML models from scratch.
- Forking and deploying a huge existing hedge-fund application wholesale.
- Options trading or short selling. Leveraged ETFs are in the candidate mapping but remain blocked by `R015` until separately approved; no leveraged execution is authorised.
- Public multi-user SaaS, billing, mobile apps or production broker support.

---

## 3. Historical strategy proposal (superseded 18 November 2026)

> This section records the original `momentum-v1` / `news-catalyst-v1` plan. Those strategies are retired from the active product; see the strategy decision above and [`docs/strategy-and-risk.md`](docs/strategy-and-risk.md).

**Proposed strategy:** Regime-aware, long-only ETF momentum using an initial universe of **SPY, QQQ and IWM**, subject to the competition's eligible-instrument list and market-data availability.

### Thesis

Short-term relative momentum may be useful when the broader market trend is favourable; reducing exposure in weak or volatile regimes may improve risk-adjusted outcomes. This is a *hypothesis*, not a claim of proven profitability.

### Initial rules to implement and test

- At each scheduled decision point, collect timestamped, available-at-decision-time market data for the chosen ETFs.
- Calculate a simple trend/regime indicator (for example: price vs. a 20-day moving average) and relative recent momentum (for example: 5-day return). **Finalize lookback windows before evaluating competition-period results** to avoid retrofitting parameters to outcomes.
- Consider a long entry only if the ETF passes the regime filter and has an eligible momentum signal.
- If no candidate passes, output **NO TRADE** with an explanation.
- Size any order under the deterministic risk policy and available settled/usable buying power.
- Define exits consistently (for example: loss of trend signal, risk stop, or scheduled rebalancing). Document exact thresholds before the first trading run.
- Execute no more frequently than needed; prioritise auditable decisions over order volume.

### Evaluation

- Record account equity using brokerage values; compare against an appropriate ETF buy-and-hold benchmark (SPY and/or QQQ), and against a cash/no-trade baseline.
- Report maximum drawdown, volatility and risk-adjusted metrics **only when the sample supports meaningful interpretation**. Show raw observations and explain limitations for the short window.
- Separate strategy returns from market exposure and any execution/data-quality issues.
- Record **every proposal**, including rejected trades and decisions not to trade.

**No performance promises.** The 17–28 November window is too short to establish statistically robust long-term profitability.

---

## 4. Architecture

```text
     Local Task Scheduler / controlled manual trigger
                           |
                [1] Coordinator agent (no tools)
                   validates run boundary
                           |
                [2] Researcher agent
          research_market → SPY bars + evidence
                           |
                [3] Risk Auditor agent
        evaluate_proposal → independent challenge
                           |
        DETERMINISTIC SIGNAL, SELECTION AND RISK GATE
             (cannot be bypassed by LLMs)
                    /             \
               REJECT            APPROVE
                 |                  |
             Audit log      Operator-only supervised CLI
                                    |
                     Paper-only broker adapter (local OAuth REST)
                                    |
                         Broker order / fill response
                                    |
                       Verify and reconcile account
                                    |
                     SQLite ledger + report pipeline
                                    |
                        FastAPI → Next.js dashboard
```

### Agent and executor responsibilities

| Role | Responsibility | Permission boundary | Output |
|---|---|---|---|
| **Coordinator agent** | Validate the run boundary and close the report from sanitized deterministic artifacts | No tools, no order permission | Run summary |
| **Researcher agent** | Review the runner-pinned SPY signal, four candidates, holding and action; capture timestamps and limitations | One read-only custom tool (`research_market`) | Structured `research_snapshot` |
| **Risk Auditor agent** | Independently challenge thesis, volatility, leverage, concentration and invalidation risk | One read-only custom tool (`evaluate_proposal`); **not** the final risk authority | Structured `risk_review` |
| **Deterministic executor** | Apply the frozen rules, enforce `RiskGate`, submit at most one approved paper order through the supervised CLI | Separate execution OAuth, both CLI flags, durable approval and every preflight check | Order events, run report |

### Non-LLM core services

- **Risk gate:** Pure deterministic code; final approval token issued only when all checks pass.
- **Broker adapter:** One audited paper-only integration point (local OAuth REST) with account lock, execution-time quote checks and a distinct read-only discovery mode.
- **Order state machine:** `PROPOSED → APPROVED/REJECTED → SUBMITTING → ACKNOWLEDGED/REJECTED → PARTIALLY_FILLED/FILLED/CANCELLED/UNKNOWN`.
- **Reconciler:** Query Moomoo account state after submissions, on scheduled sync and on restart. Treat the broker as the source of truth for fills and holdings.
- **Event ledger:** Append-only audit events; do not overwrite historical decisions or claim an order filled before confirmation.
- **Dashboard API:** Read-focused GET-only API. It has no order, approval, pause or kill-switch mutation routes.

### Structured decision contract (minimum)

```json
{
  "run_id": "unique-run-id",
  "decision_time_utc": "2026-11-18T21:00:00Z",
  "strategy_version": "spy-directional",
  "instrument": "SH",
  "action": "BUY",
  "quantity": 147,
  "signal": {"market_state": "BEARISH", "return_10d": -0.029, "sma50": 762.89, "volatility_20d": 0.2306},
  "thesis": "SPY 10-session return and trend are bearish; target inverse exposure through SH",
  "invalidation": "Exit at the next open after a neutral, opposite or volatility-ceiling signal",
  "data_as_of_utc": "2026-11-17T21:00:00Z",
  "research_evidence_ids": ["bar:SPY:2026-11-17"]
}
```

Values above reflect the observed 17 November 2026 signal recorded in the genuine run and illustrate the contract shape. Validate all fields with a schema. The agent's proposal is **not** executable until account state is refreshed and the independent gate approves it. The risk engine must recalculate quantity limits rather than blindly accepting the proposal's requested quantity.

---

## 5. Risk-control specification

### Starting limits (configurable, subject to testing)

| Control | Initial policy |
|---|---|
| Trading environment | Competition-specific **paper account only** |
| Instrument whitelist | SPY / QQQ / IWM initially |
| Per-instrument exposure | Maximum **10%** of current equity |
| Total invested exposure | Maximum **30%** of current equity |
| Open positions | Maximum **3** distinct instruments post-order |
| Account drawdown | **Pause new buying at 2% daily drawdown** from the trading day's starting equity |
| Buying power | Cash-only: reject orders exceeding `min(cash, buying_power)` after buffer; never use margin |
| First paper order | Requires explicit, durable owner approval bound to the order key |
| Short sales / leverage / options | Disabled |
| Stale or incomplete data | Block new orders |
| Position/cash mismatch | Halt new submissions until reconciled |
| Uncertain broker submission result | Enter `UNKNOWN`, query broker; **do not automatically resubmit** |
| Kill switch | Immediately block future order submissions; cancel open paper orders only when supported and verified |
| Repeated failures | Circuit-break after a configurable number of broker/tool errors |
| Order rate | Stay safely under any published competition cap |

**Important:** Pausing orders or activating the kill switch does not itself liquidate positions. Forced liquidation, if implemented, must be a separate explicit policy with its own safeguards.

### Mandatory automated tests

- Oversized proposed order rejected **before** invoking MCP.
- Missing or stale quote blocks submission.
- Insufficient buying power blocks submission.
- Duplicated agent run or retry does not create a duplicate order (idempotency guard).
- Timeout/ambiguous broker result does not trigger blind resubmission.
- Partial fill updates position and cash correctly.
- Deliberately mismatched ledger/broker positions halt new submissions.
- Drawdown threshold blocks further buys.
- Kill switch persists across process restarts.
- No configuration can redirect execution to a live account during this contest.

All exceptions and rejection reasons must appear in the ledger and dashboard.

---

## 6. Proposed stack and reuse strategy

| Layer | Proposed implementation |
|---|---|
| Agent runtime | Qoder Cloud Agents and documented Qoder skills/workflows |
| Brokerage | Competition-provided Moomoo MCP; authenticate via approved flow |
| Backend | Python 3.11+ / FastAPI / Pydantic |
| Persistence | SQLite with migrations, durable volume and append-only event records |
| Frontend | Next.js + TypeScript + Tailwind CSS + shadcn/ui, adapting the Shadcn Fintech template if its source/licence/dependencies pass review |
| Charts | Recharts or similarly lightweight plotting library |
| Local tests | pytest; mocked MCP responses; fixed test fixtures |
| Packaging | README, `.env.example`, reproducible setup scripts, optional Docker Compose |
| Reporting | Machine-readable JSON/CSV exports + Qoder-generated slide deck |

### Relevant repositories (references, not vendored)

1. **Qoder official Cloud Agents resources:** https://github.com/QoderAI/cloud-agents — local reference clone retained for documented orchestration and SDK details; not imported into the backend.
2. **Moomoo agent plugin:** https://github.com/MoomooOpen/moomoo-agent-plugin (MIT, pinned `0b28d3c23f08702fd0afae9d3a639ff0fb21290b`) — reference for Moomoo MCP tool names and payloads. The application connects directly to `https://mcp.moomoo.com/mcp`; this clone is archived outside the repository.
3. **AI Hedge Fund:** https://github.com/virattt/ai-hedge-fund (MIT, pinned `5c553b5222044f6a5527bd377b4104c50ee0ad28`) — studied for risk policy, ledger and reconciliation ideas; archived outside the repository, no code imported.
4. **TradingAgents:** https://github.com/TauricResearch/TradingAgents (Apache-2.0, pinned `9fa1196fffbcfd9de5146d2dd2869df84ab99838`) — architecture reference only; archived outside the repository.
5. **Vibe-Trading:** https://github.com/HKUDS/Vibe-Trading (MIT, pinned `a8d815d17ec054a34dbdfc7ce8d1d9972566b709`) — separate pinned research study; not a dependency and archived outside the repository.

**Reuse policy:** Build a new small repository. Copy/adapt external code only after checking source licences, attribution requirements, dependency vulnerabilities and competition rules. Prefer ideas and narrow modules over deeply coupled forks. The Qoder integration is a core execution component, not a cosmetic wrapper.

### Current repository structure

```text
mootrade/
├── README.md, plan.md, AGENTS.md, .env.example
├── docs/                     # architecture, integrations, strategy/risk, dashboard, checklist, demo
├── backend/
│   ├── app/
│   │   ├── broker/           # account lock, read-only REST, quotes, orders, OAuth
│   │   ├── research/         # spy-directional signal, dry run, evaluation, instruments
│   │   ├── risk/             # deterministic RiskGate
│   │   ├── ledger/           # append-only SQLite events, approvals, submissions
│   │   ├── dashboard/        # GET-only read models and FastAPI app
│   │   └── models/           # typed contracts
│   ├── config/               # current-market and read-only schedule configuration
│   ├── scripts/              # read-only runners, refresh, preflight, scheduler
│   └── tests/                # 310 backend tests plus fixtures
├── frontend/                 # six-page Next.js read-only dashboard
├── evidence/                 # sanitised historical runs, research, preflight, UI captures
├── data/                     # local ignored ledger and scheduler state
└── cloud-agents/             # ignored local reference clone
```

The three Qoder Cloud Agent definitions live in the Qoder platform, not in this repository; their IDs and the runner contract are in `backend/config/current_market.json` and `backend/scripts/qoder_readonly_run.py`.

Credentials, private tokens and non-public account identifiers must **never** be committed. Include sanitised evidence only.

---

## 7. Dashboard behaviour and evidence

### Overview

- Portfolio equity and cash from the latest verified broker sync.
- Open positions, pending orders and verified fills.
- Agent health, latest run status and last data-refresh timestamp.
- Clear banner when data is stale, trading is paused, or account reconciliation fails.
- Paper-trading label visible at all times.

### Risk panel

- Exposure by ticker and total portfolio exposure.
- Peak equity, current drawdown, policy thresholds.
- Current circuit-breaker and kill-switch state.
- Full rejection event with exact rule and input measurements.
- **Pause / Resume / Kill** controls (operator-only; confirm before any state-changing action).

### Decision timeline

For each run, show: source/time of market data → research conclusion → proposal → challenge/risk decision → execution order reference → broker confirmation → fill/reconciliation → resulting position. Unverified outcomes must be displayed as pending/unknown, never completed.

### Performance

- Equity curve based on broker state, not agent-generated numbers.
- Benchmark total-return comparison over exactly the same observation window.
- Cash allocation, realised/unrealised P&L if data supports it, drawdown, turnover and error counts.
- Labels explaining the limitations of a short measurement window.

---

## 8. Development plan and stage gates

### 16 November — Kickoff validation

- [ ] Create/confirm Qoder account using the competition registration email.
- [ ] Obtain Qoder Pro/credit activation, dedicated paper-account access and Moomoo MCP setup instructions.
- [ ] Confirm available MCP tools, market data, order types, account access and rate limits.
- [ ] Confirm permitted OSS reuse, submission format and required Qoder Cloud Agent evidence.
- [ ] Verify whether Cloud Agent skills/schedules and agent APIs are available on this account.

**Exit gate:** We understand the actual supported integration, permissions and contest constraints.

### 17–18 November — Connectivity and observable first trade

- [x] Create clean repository, config and basic data models.
- [x] Connect Qoder **Cloud Agent** workflow to authorised Moomoo MCP in read-only mode. Verified 17 Nov in vault-attached v4 session; the Python-to-MCP runtime bridge remains missing.
- [x] Establish a separate local REST OAuth 2.1 + PKCE read path from Python to the same competition account: DPAPI token storage, GET-only allowlist, account fingerprint, cash/positions/orders and pagination verified 17 Nov. The MCP-specific Python bridge remains unavailable.
- [x] Retrieve and log local MCP instrument quote, account balance, positions and order history (redacted shapes in `docs/integrations.md`).
- [x] Implement read-only broker adapters with strict responses, allowlists, fail-closed validation and no order-submission path; timeout/order-write handling remains for the later stage.
- [ ] Test a deliberately small paper order only after explicit local validation of account and risk conditions; verify broker acknowledgement and, if filled, the actual fill.
- [x] Event ledger, mock broker and 202 tests, including REST auth/read, read-only MCP adapter and research/dry-run tests.

**Exit gate:** Verified end-to-end paper-account interaction and an auditable trace; if order permission is unavailable, record the blocker and continue with mock tests without claiming Moomoo execution.

### 19–20 November — Strategy and non-bypassable risk

- [x] Freeze `spy-directional` entry/exit rules and the SPY/UPRO/SH/SPXU universe (documented; no parameter search).
- [x] Implement independent risk gate and persistent kill-switch state (local/mock).
- [x] Implement idempotency, order lifecycle and broker reconciliation (local/mock).
- [x] Add tests for oversizing, stale inputs, buying power, retries, unknown outcomes and mismatch.
- [x] Deterministic `spy-directional` research pipeline, historical evaluation and read-only Qoder run artifact; no order submitted.
- [ ] Deploy first full decision path from Qoder proposal through gate to paper execution.

**Critical gate — 20 November:** A scheduled or controlled Qoder run produces a proposal, enforces deterministic checks and safely attempts an approved Moomoo paper order with complete logs. **Do not prioritise visual polish before this works.**

### 21–23 November — Agent autonomy and dashboard

- [x] Implement the three bounded Qoder agent responsibilities (coordinator, researcher, auditor) with structured handoffs; execution remains deterministic Python.
- [x] Configure supported scheduling and failure reporting (local Task Scheduler, read-only).
- [x] Build six dashboard pages and all minimum read-only backend endpoints.
- [ ] Show real agent runs, real order states, account sync and rejected-risk events.
- [ ] Add audit-event exports and a first operational runbook.

**Exit gate:** Judges can understand the full trading workflow through the dashboard alone.

### 24–28 November — Paper trading, reliability and evaluation

- [ ] Run the scheduled strategy during permitted trading times.
- [ ] Verify fills, balances and positions after every order and on restart.
- [ ] Capture successful, rejected, no-trade and failed runs.
- [ ] Compare account performance to predefined benchmark and cash baseline.
- [ ] Perform controlled failure-injection demonstrations **against mocks** to avoid disturbing real competition account state.
- [ ] Make only justified, versioned strategy changes; explain what changed and why.
- [ ] Freeze representative real evidence at the end of the competition trading window.

**Exit gate:** Evidence-backed track record, risk test results and reproducible demo.

### 29–30 November — Final submission

- [ ] Freeze the strategy and release-tag the repository.
- [ ] Test clean installation and mock demo from README.
- [ ] Prepare a live-account-safe demonstration path and backup replay using sanitised historical events.
- [ ] Produce the required **Qoder-generated presentation deck**.
- [ ] Include strategy thesis, invalidation conditions, controls, actual order/fill logs and limitations.
- [ ] Verify no secrets in repository, logs, screenshots or slide deck.
- [ ] Submit the runnable agent package and deck by **30 November, 23:59 SGT**.

---

## 9. Submission and judge-demo script

### Submission package

- Runnable, documented repository with all necessary components and tests.
- Qoder Cloud Agent configuration/skills and proof of cloud runs.
- Competition Moomoo MCP integration instructions (without credentials).
- Strategy specification, position/risk limits and invalidation rules.
- Timestamped decision logs, confirmed orders/fills, account snapshots and metric calculations.
- Dashboard screenshots or working demonstration.
- Automated risk-control test results, known limitations and attribution.
- **Qoder-generated presentation** explaining architecture, performance, success cases and failures.

### Ideal 3-minute demonstration

1. **0:00–0:30 — Product:** Open dashboard; show current paper account and agent state.
2. **0:30–1:10 — Autonomous research:** Show a genuine Qoder session and structured signal/proposal.
3. **1:10–1:50 — Risk discipline:** Demonstrate a mock oversized proposal rejected *before* a broker call, with rule ID and evidence logged.
4. **1:50–2:30 — Real execution:** Show an actual approved paper order and its brokerage-reported status/fill, then reconciliation. If live market conditions are unsuitable, replay a recorded genuine execution with timestamps and say so clearly.
5. **2:30–3:00 — Reusability and results:** Show performance/benchmark, reusable skills, clean setup and one documented failure/learning.

**Do not fabricate positive returns, fills, tool calls or agent activity.** Every performance claim must be traceable to actual account observations or clearly labelled simulations/tests.

---

## 10. Success criteria

### P0 — required for a credible submission

- [ ] Qoder agents genuinely run in the required platform, with inspectable logs.
- [ ] Moomoo competition paper account is connected through the authorised integration.
- [ ] At least one end-to-end approved order path and verified resulting broker state.
- [ ] Risk gate is independent of the LLM, with tests and fail-closed behaviour.
- [ ] Decisions, orders, outcomes and reconciliation are persistently logged.
- [ ] Dashboard accurately displays account/risk/agent history.
- [ ] Repository is runnable and documents strategy, limitations and setup.
- [ ] Qoder-generated deck plus contest submission package is complete.

### P1 — strong scoring enhancements

- [ ] Scheduled autonomous runs with clear retry/error recovery.
- [ ] Reusable agent skills and versioned agent configuration.
- [ ] No-trade reasoning and a replayable rejected-trade demonstration.
- [ ] Benchmark and exposure-aware performance analysis.
- [ ] Clean design, understandable architecture diagram and polished demo.

### P2 — only if time remains

- [ ] More advanced agent debates or additional research sources.
- [ ] Enhanced alerting and historical performance analytics.
- [ ] Factor research or wider instrument universe.
- [ ] Complex interactive dashboards or multi-strategy portfolios.

---

## 11. Biggest risks and fallback plans

| Risk | Mitigation / fallback |
|---|---|
| Competition MCP differs from public Moomoo plugin | Integrate against the **actual competition tools first**; keep broker interface swappable; do not claim public plugin guarantees compatibility |
| Cloud skills/schedule access unavailable | Use documented Qoder capabilities that are accessible; show real cloud runs and document entitlement limitations |
| Missing or delayed market data | Fail closed; record a no-trade decision; never fill gaps with invented prices |
| Broker timeout or unknown order status | Block automatic retries, query order status, reconcile before continuing |
| Qoder credit exhaustion | Use cheap deterministic calculations; minimise LLM calls; schedule only meaningful sessions; cache timestamped research where valid |
| No fills in short trading window | Display actual account state and approved/no-trade decisions; demonstrate the execution path against mocks separately; disclose limitations |
| Low or negative paper returns | Explain risk-adjusted outcome honestly and show risk controls and evidence; do not chase returns with late risky trades |
| Time pressure | Protect P0: safe execution → ledger → agent runs → minimal dashboard → documentation; cut optional analytics first |
| Third-party code security/dependencies | Review narrowly reused code; pin dependencies, isolate generated code and avoid unnecessary public exposure |

---

## 12. Immediate next actions

1. **Confirm integration reality:** Qoder Cloud Agent entitlements, actual competition Moomoo MCP endpoint, paper-account verification, broker tool list and order permissions.
2. **Create the repository skeleton:** Add this `plan.md`, README, `.env.example`, models, broker adapter stubs, risk policy and tests.
3. **Build the vertical slice:** One Qoder run → one trade proposal → deterministic risk gate → one authorised paper order attempt → broker state reconciliation → log entry.
4. **Only then** add scheduled operation and dashboard.

**Definition of done:** By 30 November, MooTrade is a runnable Qoder-native autonomous paper-trading system whose decisions, risks, execution and limitations can be independently inspected—not just an impressive-looking agent dashboard.
