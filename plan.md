# MooTrade — Moomoo × Qoder AI Trading Agent Challenge

**Project plan and implementation specification**  
**Version:** 1.0 · 16 November 2026  
**Development and paper-trading window:** 17–28 November 2026  
**Submission deadline:** 30 November 2026, 23:59 SGT  
**Finalist presentations:** 8 December 2026  
**Status:** Proposed; official API access and platform details require verification at kickoff.

---

## 1. Executive summary

**MooTrade is a Qoder-native autonomous paper-trading control centre.** It uses specialised AI agents to research the market, propose trades, review decisions and generate reports, while deterministic software enforces non-negotiable risk limits. Approved orders are sent to the competition's Moomoo paper account through the authorised MCP connection. A web dashboard makes every decision, rejection, order, fill and account state visible and auditable.

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

---

## 2. End product: what the judges will see

A working **web-based trading operations dashboard** connected to the actual competition paper account and Qoder agent activity.

### Primary screens

1. **Overview** — Account equity, cash, open positions, cumulative return, maximum drawdown, active agent runs, last successful sync, paper-mode indicator and current system state (RUNNING / PAUSED / HALTED).
2. **Agent Activity** — Timestamped research runs, evidence used, trade proposals, risk approvals/rejections, execution attempts, outputs, agent/tool versions and errors.
3. **Positions & Orders** — Current brokerage-reported holdings, submitted orders, pending orders, fills, cancelled/rejected orders and reconciliation status.
4. **Risk Control** — Portfolio exposure, per-instrument limits, drawdown, configured policies, rejected proposals, kill-switch state, failure-injection test results.
5. **Performance & Reports** — Equity curve, benchmark comparison, daily returns, drawdown history, number of trades, turnover, trading costs when available, and a downloadable decision/evidence report.

### Must-have demonstration

The judges must be able to see a **real end-to-end agent decision** recorded with provenance:

`Qoder market research → structured trade proposal → independent risk check → authorised Moomoo MCP order → verified broker response/fill → ledger reconciliation → dashboard and report`

Additionally, demonstrate a deliberately **oversized order being rejected** without reaching the broker. This is a controlled test, not a fabricated trading record.

### Out of scope for this challenge

- Trading live capital or handling live brokerage credentials.
- Claiming that short paper-trading returns prove durable alpha.
- Building proprietary predictive ML models from scratch.
- Forking and deploying a huge existing hedge-fund application wholesale.
- Options trading, leverage, short selling or high-frequency strategies unless the organisers' rules and integration make them necessary.
- Public multi-user SaaS, billing, mobile apps or production broker support.

---

## 3. The trading strategy: simple, explicit and testable

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
     Qoder Cloud Agent schedules / controlled manual trigger
                           |
                   [1] Research Agent
             Data + timestamp + evidence
                           |
                   [2] Strategy Agent
              Structured trade proposal
                           |
                   [3] Risk Auditor
            Explanation and challenge
                           |
             DETERMINISTIC RISK GATE
          (cannot be bypassed by LLMs)
                    /             \
               REJECT            APPROVE
                 |                  |
             Audit log      [4] Execution Agent
                                    |
                         Broker adapter / Moomoo MCP
                                    |
                         Broker order / fill response
                                    |
                       Verify and reconcile account
                                    |
                     SQLite ledger + report pipeline
                                    |
                        FastAPI → React dashboard
```

### Agent responsibilities

| Agent | Responsibility | Permission boundary | Output |
|---|---|---|---|
| **Research Agent** | Collect market observations and current context; capture sources, timestamps and uncertainty | Read-only market data | Structured `research_snapshot` |
| **Strategy Agent** | Apply the predeclared strategy, propose candidate and rationale, or abstain | No order-submission permission | Structured `trade_proposal` / `no_trade` |
| **Risk Auditor** | Independently challenge thesis, sizing, regime and policy compliance | Read-only account/risk state; **not** the final risk authority | Structured `risk_review` |
| **Execution & Reporting Agent** | Submit only machine-approved paper orders; capture status, fills, reconciliation and readable summary | Narrow paper-order permission through one validated broker adapter | Order events, run report |

### Non-LLM core services

- **Risk gate:** Pure deterministic code; final approval token issued only when all checks pass.
- **Broker adapter:** One audited integration point for Moomoo MCP, with paper-account allowlist and a distinct read-only discovery mode.
- **Order state machine:** `PROPOSED → APPROVED/REJECTED → SUBMITTING → ACKNOWLEDGED/REJECTED → PARTIALLY_FILLED/FILLED/CANCELLED/UNKNOWN`.
- **Reconciler:** Query Moomoo account state after submissions, on scheduled sync and on restart. Treat the broker as the source of truth for fills and holdings.
- **Event ledger:** Append-only audit events; do not overwrite historical decisions or claim an order filled before confirmation.
- **Dashboard API:** Read-focused API; manual pause/resume/kill functions require deliberate operator interaction and authentication if deployed publicly.

### Structured decision contract (minimum)

```json
{
  "run_id": "unique-run-id",
  "decision_time_utc": "2026-11-18T14:30:00Z",
  "strategy_version": "momentum-v1",
  "instrument": "QQQ",
  "action": "BUY",
  "quantity": 5,
  "signal": {"regime": "positive", "momentum": "positive"},
  "thesis": "Meets predefined momentum and regime rules",
  "invalidation": "Trend filter fails or configured risk threshold triggers",
  "data_as_of_utc": "2026-11-18T14:29:00Z",
  "research_evidence_ids": ["evidence-001"]
}
```

Values above are illustrative, not observed market signals. Validate all fields with a schema. The agent's proposal is **not** executable until account state is refreshed and the independent gate approves it. The risk engine must recalculate quantity limits rather than blindly accepting the proposal's requested quantity.

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

### Relevant repositories

1. **Qoder official Cloud Agents resources:** https://github.com/QoderAI/cloud-agents — reference for documented orchestration and skills. **Verify repository contents and account access before treating any specific SDK/API as available.**
2. **Moomoo agent plugin:** https://github.com/MoomooOpen/moomoo-agent-plugin — reference for MCP account, market-data and paper-order workflows. **Verify compatibility with the competition-issued MCP and dedicated account.**
3. **AI Hedge Fund:** https://github.com/virattt/ai-hedge-fund — selectively study risk policy, ledger, state transitions and reconciliation. Do **not** substitute its internal simulated account for Moomoo's competition account.
4. **Vibe-Trading (optional):** https://github.com/HKUDS/Vibe-Trading — reference for finance-tool organisation, risk analytics and dashboard concepts. Do not install wholesale unless it saves time and passes security/dependency review.

**Reuse policy:** Build a new small repository. Copy/adapt external code only after checking source licences, attribution requirements, dependency vulnerabilities and competition rules. Prefer ideas and narrow modules over deeply coupled forks. The Qoder integration is a core execution component, not a cosmetic wrapper.

### Suggested repository structure

```text
mootrade/
├── README.md
├── plan.md
├── AGENTS.md
├── .env.example
├── docs/
│   ├── architecture.md
│   ├── integrations.md
│   ├── strategy-and-risk.md
│   ├── dashboard.md
│   ├── build-checklist.md
│   ├── judge-demo.md
│   ├── incidents-and-limitations.md  # build as incidents occur
│   └── attribution.md               # build if code/assets reused
├── agents/
│   ├── research/
│   ├── strategy/
│   ├── risk-auditor/
│   ├── execution-reporter/
│   └── skills/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── broker/
│   │   ├── risk/
│   │   ├── strategy/
│   │   ├── ledger/
│   │   ├── reconciliation/
│   │   └── models/
│   └── tests/
├── dashboard/
├── evidence/
│   ├── sanitized-agent-runs/
│   ├── risk-test-results/
│   └── sample-reports/
└── scripts/
```

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

- [x] Freeze `momentum-v1` entry/exit rules and instrument universe (documented; no parameter search).
- [x] Implement independent risk gate and persistent kill-switch state (local/mock).
- [x] Implement idempotency, order lifecycle and broker reconciliation (local/mock).
- [x] Add tests for oversizing, stale inputs, buying power, retries, unknown outcomes and mismatch.
- [x] Deterministic research pipeline (`momentum-v1`, `news-catalyst-v1`), historical evaluation and dry-run report (`evidence/sample-reports/decision-report-2026-11-17.md`); no order submitted.
- [ ] Deploy first full decision path from Qoder proposal through gate to paper execution.

**Critical gate — 20 November:** A scheduled or controlled Qoder run produces a proposal, enforces deterministic checks and safely attempts an approved Moomoo paper order with complete logs. **Do not prioritise visual polish before this works.**

### 21–23 November — Agent autonomy and dashboard

- [ ] Implement the four bounded agent responsibilities with structured handoffs.
- [ ] Configure supported cloud scheduling and failure reporting.
- [ ] Build five dashboard screens and all minimum backend endpoints.
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
