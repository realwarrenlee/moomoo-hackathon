# Strategy and risk specification

**Active strategy:** `spy-directional` — deterministic daily S&P 500 directional research through SPY, SH or CASH, with **risk-v3 only** tiered sizing: 0% cash or 10%–40% of equity, 1x instruments only. Risk-v1 is retired; the pre-simplification risk-v2 (20% floor, 150% ceiling, 3x leverage, UPRO/SPXU selection) was replaced by **risk-v3 on 20 November 2026** and is **HISTORICAL** evidence only.

**Current mandate (20 November 2026):** risk-v2 was simplified to risk-v3 — SPY bullish / SH bearish / CASH when no valid trade, allocations 10%–40%, no leveraged ETFs, no margin/short/options, one directional ETF position at a time. UPRO/SPXU were removed from the candidate universe, instrument selection, supervised execution allowlist, automated paper-trading eligibility and decision-generation paths; their historical audit records and evidence are preserved unchanged. The stale 576-SH BUY approval (`spy-directional-2026-11-19-SH-BUY`, old 20% weak tier) was superseded in the append-only ledger (1:37Z, `APPROVAL_SUPERSEDED` event) and can no longer authorise an order. Explicit, durable owner approval for **EVERY supervised BUY and SELL**, bound to the exact proposal and client order key, remains required; `TRADING_MODE=SUPERVISED_PAPER` and `ORDER_WRITES_ENABLED=false` remain unchanged. The 18 November 2026 23:58Z pre-simplification risk-v2 pin is retained as a **HISTORICAL** record, not current unattended authority. No automatic return to `AUTO_PAPER` is authorised; future autonomy requires separate explicit approval.

## One-page strategy specification

**Hypothesis:** a persistent 10-session S&P 500 move, confirmed by price relative to its 50-session trend, can be followed with one directional ETF sized to the strength of the signal, subject to volatility and portfolio controls.

**Decision sequence (risk-v3):** (1) analyse SPY; (2) determine BULLISH/BEARISH/NEUTRAL; (3) determine strength/risk; (4) calculate a **target signed S&P 500 exposure fraction** (0% or ±10%–±40%); (5) choose SPY (bullish) / SH (bearish) / CASH; (6) compute cash allocation and whole shares; (7) apply RiskGate; (8) obtain explicit owner approval for the exact BUY/SELL proposal/key and execute only through the supervised paper boundary with fresh preflight; (9) monitor and propose exits/resizes, each requiring its own approval.

| Question | Deterministic answer in `spy-directional` |
|---|---|
| What is measured? | SPY's 10-session `close/close` return, its 50-session simple moving average and its 20-session annualised realised volatility, all from completed daily bars. |
| Direction (risk-v3)? | The sign of the 10-session return: `>= +1.5%` BULLISH, `<= -1.5%` BEARISH, otherwise NEUTRAL/CASH. |
| Volatility gates? | 20-session annualised volatility above `40%` forces CASH. |
| Target exposure? | Tiered by the absolute 10-session return (risk-v3): below `1.5%` → `0%` (CASH); `1.5–3%` → `10%` (weak); `3–5%` → `25%`, trend-confirmed `40%` (moderate); `5–8%` → `40%` (strong); `>= 8%` → `40%` (exceptional, capped). All tiers are the fraction of **equity** in signed S&P 500 exposure; nothing can exceed `±40%`. |
| Which ETF? | SPY (bullish) / SH (bearish), 1x only. UPRO/SPXU are outside the risk-v3 universe. |
| Cash allocation? | `equity × |target|` — a 40% target spends 40% of equity on SPY or SH; a 10% target spends 10%. Whole shares, cash-only, never margin. |
| BUY / SELL / HOLD / CASH? | BUY when flat and a target is selected; HOLD when the target equals the held ETF; SELL when the held ETF is no longer the target or the target is CASH. One directional position at a time. |
| Reversal? | A SELL or CASH decision comes first. The opposite entry is considered only by a later run that observes a confirmed flat broker position. |
| Resize? | Deterministic rules only, never discretionary LLM instructions: a tier move on the same held symbol resizes when the share delta is `>= 1` share and `>= 5%` relative (SELL excess or BUY top-up); a direction flip SELLs first. |
| Who decides? | Deterministic code computes the signal, tier, selection, sizing and state transition. Three Qoder agents reason and challenge. The RiskGate is final. |

### Signal and eligibility

- Evaluate once after a session closes. The bar file must end on the latest completed US session, contain at least `51` sessions, and contain both SPY and SH bars.
- Tier criteria are transparent and reproducible from the existing return/trend/volatility measurements. An LLM confidence percentage is never equated with an empirically calibrated probability of success.
- No intraday signal, parameter search or unregistered strategy is used.
- An agent may describe or challenge the signal but cannot change the computed direction, target, quantity or controls.
- Missing, stale or incomplete data abstains; it never fabricates a bar, quote, fill or decision.
- The same daily signal never generates repeated intraday BUY orders. Position adjustments follow the explicit deterministic resize rules above.

### Instrument universe and verified mapping

Both positions are opened with **BUY** orders. SH has negative economic direction but is still bought, never shorted. Effective exposure is `direction × daily leverage`.

| Symbol | Benchmark | Direction | Daily leverage | Effective exposure | Status |
|---|---|---:|---:|---:|---|
| SPY | S&P 500 | +1 | 1x | +1x | risk-v3 universe; quote/history verified; read-only MARKET cash-buy capacity verified 19 Nov; no fill claimed |
| SH | S&P 500 (inverse) | -1 | 1x | -1x | risk-v3 universe; quote/history verified; read-only MARKET cash-buy capacity verified 19 Nov; broker refused all five sanctioned pre-simplification submissions with `ret_code=-5` (backend business error); cause verified 20 Nov via the official handbook: competition stock/ETF exposure is capped at **40% of total initial account assets**, so the 1,764-share (~60%) entry was rejected; risk-v3 tiers stay within ±40%, so `R019` is the binding ceiling; no fill claimed |

UPRO and SPXU were part of the pre-simplification risk-v2 universe; risk-v3 removed them entirely and their proposals are rejected by default-deny symbol validation. Their read-only quote/book/session observations remain **HISTORICAL** evidence in [`docs/integrations.md`](integrations.md).

The earlier verified snapshot contains 370 read-only Moomoo daily bars per symbol through 17 November 2026; latest completed bars end on 18 November (decision below). Quote, order-book and market-state observations are recorded in [`docs/integrations.md`](integrations.md). Metadata lives in [`backend/app/research/instruments.py`](../backend/app/research/instruments.py). Quote support does not establish competition-account execution acceptance. The prepared SPY/SH execution scope grants no order permission; each BUY/SELL still needs approval. QQQ is preserved for historical diagnostic reconciliation only. CASH is always permitted.

### State machine, sizing and costs

**Active risk-v3 tiered sizing:**

- Target exposure fraction `f` (signed) comes from the tier table: below `1.5%` → `0%`; `1.5–3%` → `10%`; `3–5%` → `25%` (trend-confirmed `40%`); `5–8%` → `40%`; `>= 8%` → `40%`. The selected ETF is SPY for `f > 0` and SH for `f < 0`, both 1x. Nothing can exceed `±40%` of equity.
- **Competition concentration cap (verified 20 Nov 2026):** single-security stock/ETF exposure may not exceed **40%** of account value, enforced on entry. Sizing (fresh BUY and resize targets) is clamped so `price × quantity` stays at or below 40% of equity, and the declared target is recomputed from the capped quantity so `R018` stays consistent. A held position that is above the cap (e.g. after price movement) is trimmed back to it on the next resize check. The gate independently enforces the cap on entry (`R019`), counting the existing position and same-symbol pending BUYs.
- **Cash allocation** is `equity × |f|`; quantity is floored to whole shares at the **bar close** of the selected ETF.
- **Flat + target:** BUY the selected ETF.
- **Held ETF equals target:** HOLD, with no order generated.
- **Held ETF differs from target, or target is CASH:** SELL the held ETF. The opposite entry is not submitted in the same run.
- **Reversal:** a later run may BUY the opposite ETF only after read-only reconciliation confirms the prior position is flat.
- **Same-symbol resize:** tier moved `>= 1` share and `>= 5%` relative → SELL the excess or BUY the top-up with the same signal. Top-up BUYs carry no declared target, so `R018` is not applicable; `R017` still checks the post-order signed total.
- **Multiple holdings, working orders or unreconciled state:** fail closed with no new order.
- Only one directional S&P 500 position may exist at a time; bullish and bearish ETFs are never held simultaneously.
- Evaluation charges 2 bps per side. Spread, slippage and inverse-ETF daily rebalancing costs are not modelled; this is a limitation, not an estimate of profitability.

**Concentration risk (explicit):** a `40%` exposure can lose approximately `0.8%` of portfolio equity on a `2%` adverse daily index move (and approximately `1.6%` on a `4%` move). The 2% daily-drawdown brake halts new buying — it does **not** guarantee losses stop at 2%, and stop-losses do not eliminate overnight gap risk.

### Deterministic authority and agent roles

- **Market Researcher:** reviews the runner-pinned SPY return, trend, volatility, two-candidate eligibility, current holding and action; produces a timestamped assessment.
- **Independent Risk Auditor:** challenges the thesis, contradictory evidence, stale data, concentration, leverage, drawdown, invalidation and downside; calls `evaluate_proposal` when a proposal exists.
- **Coordinator:** combines the research, counterarguments and deterministic output into `BUY`, `SELL`, `HOLD` or `NO_TRADE` with traceable reasoning. It has no tools.
- **Deterministic code:** signal arithmetic, tier calculation, ETF selection, sizing, HOLD/SELL/CASH/reversal state, resize/duration rules, RiskGate enforcement, the supervised execution command and order permissions. The RiskGate is final and cannot be overridden by an agent, UI text or research content.
- **Adaptation:** agents reason only. They cannot write bars, alter the computed signal or access broker order tools. All three agents are read-only with respect to order permissions.

### Active risk-v3 policy only

Research and execution use risk-v3, not a policy selected by a historical `TradingActivation`. The 18 November 16:03Z risk-v1 row and the 18 November 23:58Z pre-simplification risk-v2 row remain **HISTORICAL** and append-only; neither can govern new research or execution or be reactivated. Their old sizing and single/gross caps are not operative controls. `latest_trading_activation` returns the risk-v3 pin only when its policy version and limits match the current defaults exactly.

| Area | Active mandate |
|---|---|
| Research symbols | SPY, SH |
| Prepared supervised execution scope | SPY/SH only; UPRO/SPXU are outside the risk-v3 universe and rejected by default-deny symbol validation |
| Research targets | tiered `0%` / `10%` / `25–40%` / `40%` signed-exposure magnitude |
| Exposure controls | `R016` 10% floor (skipped only by supervised path), `R017` 40% signed-effective ceiling, `R018` declared-target tolerance ±5 percentage points, `R019` competition 40% single-security concentration cap |
| Position count | RiskGate maximum one; strategy maximum one directional position |
| Daily drawdown | `R006` 2% halts new buying |
| Cash / freshness | US$5 cash buffer; quote ≤300 seconds; account snapshot ≤60 seconds |
| Owner approval | `R014` durable approval for the exact proposal/key of EVERY supervised BUY and SELL |

- `R015` rejects any leverage above the 1x daily maximum; the risk-v3 model's ceiling is 1x and leveraged funds are outside the universe.
- `R016`/`R017` measure **signed effective exposure** (`price × quantity × leverage × direction / equity`); the ceiling applies to the magnitude of the post-order signed total. `R018` compares an initial BUY's signed exposure against its declared target within `±0.05`; resize top-ups and SELLs carry no declared target. `R019` measures **per-security notional exposure** (`price × quantity` on the entry symbol, plus the existing position value and same-symbol pending BUYs) against 40% of equity and applies to BUYs only. Only the supervised path skips the floor, not the ceiling, target consistency or concentration cap.
- `R008` requires unlevered cash (`min(cash, buying_power) − US$5 buffer`) for actual notional; no margin is used.
- Per-symbol leverage metadata is validated; invalid or non-positive metadata rejects with `R007`.

### Daily risk monitoring (read-only)

A dedicated read-only monitor (no order-write capability) runs in three ET windows via Windows Task Scheduler (dual-DST triggers):

| Window | Checks |
|---|---|
| Reconcile `09:45–10:30` | Reconciles `SUBMITTING`/`ACKNOWLEDGED`/`PARTIALLY_FILLED`/`UNKNOWN` submissions against broker state; reports unresolved ambiguous submissions. |
| Midday `12:00–13:00` | Active v2 2% daily drawdown and signed-effective exposure breaches; 1x-universe holding-duration check (inert: SPY/SH only, no leveraged funds); open-order leftovers. |
| Pre-close `15:45–16:00` | Same as midday **plus** unresolved ambiguous submissions and leftover open orders. |

Breach policy: exposure, duration and open-order breaches are **reported only** (`RISK_BREACH` events); resulting reductions/exits are proposals that still require exact-proposal/key owner approval. The **persistent kill switch engages** when daily drawdown reaches the limit or ambiguous submissions remain unresolved at pre-close. It blocks new writes, including exits, and never liquidates implicitly. The monitor is read-only and refuses order-write scope or `ORDER_WRITES_ENABLED=true`. The monitor skips symbols outside the risk-v3 universe (e.g. historical UPRO/SPXU holdings) instead of crashing.

### Research evidence and limitations

- **Latest completed bars (18 November 2026):** SPY close `730.2`, 10-session return `-4.7743248%`, SMA50 `762.2828597323`, annualised volatility `22.8820254%`. Under the **pre-simplification risk-v2 tiers** (HISTORICAL: 20%/40–60%/80–100%/100–150%) this was BEARISH with an SH target of **−60% signed exposure**; the genuine three-agent run `qoder-4e73fe0c-6d70-4722-84ac-aaf0f9dc1b3e` proposed BUY 1,764 SH. The 15:02Z broker-backed supervised preview estimated $59,561.46 at SH 33.765 (−59.5668% exposure) and rejected missing exact-order approval; actual writes remained disabled. This is not a fill or guaranteed acceptance. **Under risk-v3 the same measurements map to the `3–5%` MODERATE band: −25% base, −40% trend-confirmed (close is below the SMA50, so the bearish trend confirms).** The current decision is regenerated by the standard workflow before any proposal — see `docs/evidence.md`.
- **HISTORICAL inputs:** 370 completed bars each for SPY/UPRO/SH/SPXU through 17 November, in `evidence/current-market/2026-11-17/daily-bars.json` and [`backend/tests/fixtures/moomoo_directional_etf_bars_2026-11-17.json`](../backend/tests/fixtures/moomoo_directional_etf_bars_2026-11-17.json). The prior IWM/QQQ/SPY snapshot remains as `daily-bars-iwm-qqq-spy-prior.json`.
- **HISTORICAL rejected decision:** 17 November close `732.44`, return `-2.90%`, SMA50 `762.89`, volatility `23.06%` → SH, 147 shares at retired 5% sizing. The real gate rejected it (`R002`, stale post-close quote, non-regular session, `R010`, `R014`). Do not treat it as an executable v2 proposal.
- **HISTORICAL sanity check, not v2 performance:** 12 August 2025 to 17 November 2026 at the frozen old rules and 5% sizing produced `-0.40%` total return, `0.42%` annualised volatility, `-0.75` Sharpe, `0.59%` maximum drawdown, `41.07%` of sessions exposed, 35 trades and a `41.18%` win rate. SPY buy-and-hold returned `+15.47%` with `8.88%` maximum drawdown. These unchanged results underperformed; they are neither alpha nor paper-account evidence and were not optimised.
- **HISTORICAL genuine read-only demo:** `qoder-328aefff-7dde-4a98-ac76-99b3e0e33728` (18 November 2026) recorded that SH proposal and rejection, not the latest −60% v2 target. It placed no order. See [`evidence/qoder/`](../evidence/qoder/).
- **Forward strategy paper validation** is pending. QQQ diagnostic BUY `3115842` and SELL `3115920` both filled and reconciled on 18 November, but are not strategy performance or SPY/SH acceptance.
- **Acceptance requirements:** only explicitly eligible instruments may reach `APPROVE`; every decision is traceable; EVERY supervised BUY/SELL has its own exact-proposal/key owner approval. Current test results, verified SPY/SH capacity and the genuine submission-disabled SH preview are recorded in `docs/evidence.md`.
- **Rejection:** negative net return over a 20-trade forward sample, drawdown beyond policy, repeated inability to produce traceable decisions, or failure to beat cash/exposure-matched benchmarks. Thresholds must not be tuned on backtest outcomes.

### Retired strategies and simplification audit

- **Retired from the active product:** `momentum-v1`, `news-catalyst-v1`, `directional-event-v2`, `volume-confirmed-relative-strength-v1`, `moomoo-oversold-reversal-v1`, and the research-only `etf-trend-baseline-v1` comparator.
- **Removed:** the event archive, event module, synthetic event fixture, old demo/report generators, momentum deployable-limit study, catalyst study, Moomoo-signal observation script, obsolete archive types and their strategy-specific tests.
- **Retained as historical evidence:** prior research artifacts and Qoder runs under `evidence/`, the ETF baseline study/comparator, buy-and-hold and cash baselines, risk/execution history and supervised diagnostic records.
- **Reused:** `MarketHistory`, read-only Moomoo feeds, the dry-run harness, Qoder tool boundary, deterministic `RiskGate`, paper executor, ledger, reconciliation and the existing dashboard.
- **HISTORICAL cleanup scope:** that strategy cleanup did not change OAuth scopes, broker adapter, order transport, supervised workflow, kill switch, dashboard structure or agent count. The current mandate separately requires every-order approval and the exact proposal-file handoff described above.

## Active hard constraints

| Rule ID | Limit | On breach |
|---|---|---|
| R001 | Exact verified competition paper account (masked id + fingerprint, simulated source) | Reject and disable order writes |
| R002 | Execution allowlist is SPY/SH only; the risk-v3 universe contains no other symbols | Reject |
| R003 | Long-only, cash-only; no options, short selling, margin or leveraged funds | Reject |
| R006 | Daily equity drawdown >= 2% from the trading day's starting equity | Pause new buying; no implicit liquidation |
| R007 | Missing/invalid/contradictory inputs, quote >300s or account snapshot >60s | Reject/abstain |
| R008 | Insufficient unlevered cash after US$5 buffer | Reject |
| R009 | Reconciliation mismatch, unknown order or unreadable broker state | Halt new submissions |
| R010 | Persistent kill switch on, circuit breaker open or writes disabled | Reject all submissions |
| R011 | Duplicate run/approved proposal/order key | No duplicate submit |
| R012 | Exchange/session constraints or ineligible order type | Reject |
| R013 | Post-order positions >1 distinct instrument; strategy separately allows only one directional position | Reject new buying |
| R014 | Any BUY or SELL without a durable exact-proposal/key owner approval (supervised) or a valid, unexpired risk-v3 activation pin bound to the account fingerprint, strategy version, symbol allowlist and limits (autonomous; never on the supervised gate) | Reject before broker call |
| R015 | Leverage above the approved 1x daily maximum | Reject before broker call |
| R016 | Research exposure floor 10%; skipped only in the supervised path | Reject when applicable |
| R017 | Magnitude of post-order signed-effective exposure >40% of equity | Reject |
| R018 | Initial BUY differs from declared signed target by >5 percentage points | Reject |
| R019 | Post-order single-security exposure >40% of equity — competition stock/ETF concentration cap, entry-enforced and verified from the official handbook 20 Nov 2026; counts the existing position and same-symbol pending BUYs, exempt for SELLs | Reject |

Retired risk-v1 rule IDs and limits may appear in **HISTORICAL** artifacts; they are not selectable executable policy. No LLM, agent administrator or dashboard button may bypass current controls. Limit or permission changes require explicit owner approval and audit evidence.

**Cash-only note:** the competition account may be margin-type. R008 uses `min(cash, buying_power) − US$5 buffer`, so broker margin is never used.

### How quantity is computed

1. Resolve the exact competition paper account by trusted metadata, masked id and SHA-256 fingerprint.
2. Get fresh broker-confirmed equity, day-start equity, holdings, pending orders and buying power.
3. Compute the risk-v3 tiered signed target (0% or ±10%–±40%); select SPY or SH and floor `equity × |target| / price` to whole shares, then clamp the quantity to the competition 40% single-security cap (recomputing the declared target from the capped quantity). Research uses the completed bar close; execution rechecks using a fresh quote.
4. Independently validate post-order signed-effective exposure, target consistency, position count and cash headroom including pending exposure; do not substitute retired single/gross caps.
5. Abstain if fewer than one valid share or any applicable rule fails. Only the supervised path skips the floor; other safeguards remain.
6. Bind the risk decision to the current proposal/account snapshot and re-evaluate after its 30-second TTL or a state change.

EVERY supervised BUY and SELL also requires durable owner approval for the exact proposal and `client_order_key` (`R014`). The historical CLI name `approve-first-order` remains, but is used for each order. **Owner approval does not expire with the 30-second risk TTL**; it never authorises another proposal/key or submits an order. In `AUTO_PAPER` only, a valid unexpired risk-v3 activation pin (time-limited, bound to the account fingerprint, strategy version, SPY/SH allowlist and the pinned 10%/40%/2% limits) replaces per-order approval; it is re-validated deterministically on every run and never satisfies `R014` on the supervised gate.

## Fail-closed order flow

`proposal → schema validation → snapshot refresh → risk policy → durable approval and idempotency key → paper write → broker status refresh → reconciliation → event + report`

If the broker call times out, status is **UNKNOWN**. Do not send a replacement order until a status query and account reconciliation rule out the original. Acknowledgement does not equal fill.

### Execution-time preflight

Before any order can be submitted, the executor must obtain a fresh quote for the exact symbol (no older than 300 seconds, not future-dated, positive price, normal trading status, not suspended) and confirm the regular US session from the provider's market-state response. Only `AFTERNOON` is accepted as regular hours; the provider defines it as 09:30–16:00 ET. A closed session, stale quote, malformed market state or unreadable account snapshot blocks execution before the broker adapter is reached.

### UNKNOWN submission handling

A timeout or malformed broker response is persisted as `UNKNOWN` before any further action. While any `UNKNOWN` submission exists, all new submissions are rejected (`R009`). Reconciliation queries three broker sources — today's orders, order history and the account snapshot/positions — and requires the snapshot's paper environment and account fingerprint to match the submission. It then matches exactly one broker order by the correlation tag carried in the documented `text` remark and validates symbol, side and quantity against the local request. Zero matches stays `UNKNOWN` (no match); more than one match is ambiguous and also stays `UNKNOWN`; an account mismatch stops reconciliation. Neither case retries the order. A unique match is written to the ledger only if the provider status transition is legal. The remark is a correlation aid, not a broker-enforced idempotency key.

Runtime remains `SUPERVISED_PAPER` with `ORDER_WRITES_ENABLED=false`. The guarded supervised transport has broker-observed QQQ diagnostic fills, not SPY/SH strategy acceptance. The prepared preview/execute `--proposal-file` handoff preserves the exact research timestamps, evidence and target, and rejects any required CLI-field mismatch. Preview reports per-rule states and current/post signed-effective exposure with `submission_performed: false`; it grants no approval and submits nothing. No new order or activation is claimed.

## Pausing vs killing

- `PAUSED`: no new order submissions; continue read-only sync, audit and reporting.
- `HALTED`: persistent safety interlock; manual review and preflight required to resume. Display prominent warning.
- `KILL`: operator-triggered persistent stop of new writes. If cancellation is supported, separately offer documented authorised cancellation of pending orders.
- None of these states implicitly means existing holdings have been liquidated.

## Appendix: historical evidence for retired strategies

> **HISTORICAL — retired, not executable.** The evaluations, limits, blockers and recommendations below describe their dates, not current behaviour. Results and frozen comparator sizing are unchanged. Risk-v1 cannot be selected or reactivated; its old limits are not active controls. `spy-directional` with risk-v2 is the only active strategy/policy.

## Evaluation metrics

Use confirmed paper account data with timestamped observations. Report time-weighted return only when equity history and flows permit; otherwise explicitly state the calculation. Include max drawdown, cash exposure, rejected/approved/no-trade decisions, filled orders, execution errors, and benchmark comparison over exactly matched dates. Do not overinterpret Sharpe/Sortino from ~2 weeks of observations. Include raw equity series and limitations.

## First evaluation (17 November 2026)

The deterministic pipeline was evaluated on the committed 370-session fixture (2025-05-29 to 2026-11-16) with next-open execution, 2 bps per side, fractional shares and no leverage or shorting. This is a **signal-quality study**, not the return of the risk-gated paper account; the 10% single-instrument and 30% gross caps were not applied.

| Strategy / baseline | Period | Signals | Total return | Max drawdown |
|---|---|---:|---:|---:|
| `momentum-v1` | 2025-06-27 to 2026-11-16 | 23 | -0.41% | 11.68% |
| `momentum-v1` | 2026-02-10 to 2026-11-16 | 13 | -3.77% | 11.68% |
| `news-catalyst-v1` | 2026-02-10 to 2026-11-16 | 7 | +1.56% | 11.03% |
| SPY buy-and-hold | 2025-06-27 to 2026-11-16 | 1 | +19.83% | 9.13% |
| SPY buy-and-hold | 2026-02-10 to 2026-11-16 | 1 | +6.23% | 9.27% |
| QQQ buy-and-hold | 2026-02-10 to 2026-11-16 | 1 | +7.34% | 14.82% |
| Cash | 2026-02-10 to 2026-11-16 | 0 | 0.00% | 0.00% |

Both strategies underperformed a simple SPY holding in these windows. The last completed session (2026-11-16) produced `NO_TRADE` because SPY closed below its 20-session SMA. The news archive is sparse and asymmetric (QQQ headlines begin only on 2026-10-06), the keyword sentiment score is a crude proxy, and 17 months of three ETFs cannot establish durable alpha. Parameters were frozen before evaluation; no search or retrofitting was performed. Full tables, accepted hypothetical proposals and rejection evidence are in `evidence/sample-reports/decision-report-2026-11-17.md`.

## Deployable-limit re-evaluation (18 November 2026)

The signal-quality study above used all available cash and fractional shares; it reached 65.71% average exposure and 100% maximum exposure. The deployable RiskGate is materially tighter. This re-evaluation applies the actual limits without changing the frozen `momentum-v1` rules: 10% of equity per position, 30% gross, at most three positions, whole shares, cash only, next-open execution and 2 bps per side. It uses the same 370-bar fixture (349 evaluated sessions from 2025-06-27 to 2026-11-16) and the same 23 entries.

| Series | Total return | Max drawdown | Avg exposure | Max exposure | Entries |
|---|---:|---:|---:|---:|---:|
| `momentum-v1`, deployable limits | +0.09% | 1.22% | 6.62% | 11.25% | 23 |
| SPY hold, 10% entry | +2.07% | 1.02% | 11.29% | 12.37% | 1 |
| SPY hold, 6.62% entry (approximate exposure match) | +1.37% | 0.68% | 7.51% | 8.27% | 1 |
| SPY hold on the strategy's exact entry/exit sessions, 10% | +0.43% | 0.97% | 6.53% | 11.24% | 23 |
| Cash | 0.00% | 0.00% | 0.00% | 0.00% | 0 |

Compared with the prior 100%-notional study, total return changes from `-0.41%` to `+0.09%` (+0.50 pp), maximum drawdown from `11.68%` to `1.22%` (-10.46 pp), and average exposure from `65.71%` to `6.62%` (-59.09 pp). This is mostly a sizing effect, not a new signal: the strategy is out of the market most of the time, and its small positive result still loses to every SPY comparator over the same dates. The decisive comparator is the same-schedule SPY holding, which controls for both entry/exit dates and exposure: it returned `+0.43%` at `6.53%` average exposure versus `+0.09%` for `momentum-v1`. The 30% gross cap and three-position limit never bind because the frozen strategy holds at most one ETF. Whole-share flooring and rising prices caused close-of-day exposure to drift to `11.25%`; the entry cap remains 10%.

This is not new out-of-sample evidence and the holdout was not re-tuned. Artifacts, raw equity curves and trades are in `evidence/research/momentum-deployable-2026-11-18/`.

## Proposed stock-selection hypothesis (pre-registered, not deployed)

`volume-confirmed-relative-strength-v1` is a single, frozen research hypothesis, recorded before any evaluation. It is **not** an executable strategy, has no backtest result and must not be described as alpha.

**Hypothesis:** among a fixed liquid large-cap universe, stocks with positive 20-session relative strength, a close above their 50-session SMA and broadening 5-session volume may continue to outperform over the next week. Volume expansion is a participation check, not a proven predictor.

**Rules (all computed from completed daily OHLCV bars):**

1. Evaluate after the last completed session of each week. Require `SPY close > SPY 200-session SMA`; otherwise target cash.
2. A stock qualifies if `close > 50-session SMA`, its 20-session return is positive, and `mean(volume[t-4..t]) >= 1.2 * mean(volume[t-24..t-5])`.
3. Rank qualifiers by 20-session return descending, then symbol ascending; select the top three. Hold fewer if fewer qualify; never substitute an unqualified name.
4. At the next session open, hold each selected name at 10% of current equity, maximum three names and 30% gross, whole shares and cash only. Rebalance weekly; if the SPY regime turns false, sell all at the next open.
5. Costs: 2 bps per side. No intraweek stop, leverage, shorting or options.

**Universe (fixed before evaluation):** `AAPL, AMD, AMZN, AVGO, COST, GOOGL, HD, JNJ, JPM, MA, META, MSFT, NFLX, NVDA, PG, TSLA, UNH, V, WMT, XOM`. This is not a point-in-time index membership list; survivorship and selection bias are explicit limitations.

**Data and evaluation:** the only inputs are raw Moomoo `history-kline` daily OHLCV fields (date, open, high, low, close, volume), which are independently reconstructable. The pre-registered window is `2016-01-04` to `2024-12-31`, separate from the ETF holdout; 2025-2026 data is not used to tune or validate this protocol. Run once with no parameter search and no changes after the first result. Benchmarks are same-schedule SPY at the strategy's weekly gross exposure, constant 30% SPY, an equal-weight fixed universe on the same schedule and cash. If the run does not beat the same-schedule SPY and equal-weight comparators after costs, or depends on a handful of trades, reject it and do not tune it on that window.

**Moomoo boundary:** `kline-shape` pattern labels, `indicator-polarity` labels, `indicator-backtest` statistics and capital-flow categories are not signal inputs. A timestamped pattern or indicator reading may be retained as research context, but it must not create, veto or rank a signal. No provider success rate is treated as historical evidence.

**Deployment blockers:** the RiskGate allowlist remains `{SPY, QQQ, IWM}`; adding stocks requires an owner-approved universe expansion. The simulated-order transport is disabled and provider-unproven, `ORDER_WRITES_ENABLED=false`, and the first paper order still requires explicit owner approval and execution-scope consent. The protocol is in `evidence/research/stock-selection-prereg-2026-11-18/protocol.json` with SHA-256 `4a9791b82fdc2829deb74d5e0dc3c287f9ab746ae023c047a0c2cd7f9a82fce0`. It has not been evaluated or deployed.

## ETF trend baseline (separate research study, 17 November 2026)

`etf-trend-baseline-v1` is a **HISTORICAL**, frozen low-turnover comparator. Its 10% study sizing is unchanged, not executable risk-v1 or an active RiskGate limit. It has no registered strategy, proposal builder or order path.

- At each completed month-end, the study holds `SPY` only above its 200-session SMA; otherwise cash.
- The study executes a changed signal at the next session open, maximum `10%` of equity at entry; 2 bps per side; fractional shares.
- No parameter search was performed. The 200-session and monthly choices were fixed before producing this study.

| Series | Period | Entries | Total return | Max drawdown | Avg exposure | Turnover |
|---|---|---:|---:|---:|---:|---:|
| `etf-trend-baseline-v1` | 2026-04-01 to 2026-11-16 | 1 | +0.26% | 0.63% | 9.04% | 0.0996 |
| SPY hold, 10% | same | 1 | +1.31% | 0.69% | 11.26% | 0.0986 |
| SPY hold, 100% (reference) | same | 1 | +13.14% | 5.92% | 100.00% | 0.8754 |
| Cash | same | 0 | 0.00% | 0.00% | 0.00% | 0.0000 |

The baseline entered on 1 May 2026 after the 30 April signal and remained open at the end of the fixture. It avoided most of April's decline but missed the recovery before its next-open fill, and it underperformed both matched SPY holdings. This is a signal-quality study, not a paper-account return.

Limitations: only seven monthly decisions after the 200-session warmup; one entry cannot establish alpha; the 10% cap is enforced at entry but mark-to-market exposure drifted to 10.71%; monthly decisions can miss fast reversals; dividend/tax treatment depends on the adjusted fixture bars; descriptive Sharpe is not statistically meaningful. Artifacts are under `evidence/research/etf-trend-baseline-2026-11-17/`.

## Strategy review (18 November 2026)

Question: is the existing ETF momentum strategy defensibly better than a simple alternative, or should it stay in `NO_TRADE`? Frozen artifacts only; no parameter was changed or re-optimised and no new strategy was registered.

### Regime-filter audit

Across the 370-session fixture, 350 sessions had enough history to evaluate the `SPY > 20-session SMA` filter:

- 233 sessions were regime-positive and 117 regime-negative, with 57 switches.
- Forward 5-session SPY return from the next open: positive regime mean `+0.14%` (58.8% of windows positive) versus negative regime `+0.41%` (59.1%).
- Forward 20-session: `+0.92%` versus `+1.27%`.
- In the holdout window (2026-04-01 onward) the regime was positive on 62.3% of sessions and switched 28 times.

In this sample the filter does not improve forward index returns, and the difference is smaller than the noise of overlapping windows. It still serves a legitimate purpose as a deterministic exposure brake, but it is not evidence of alpha. The 2026-11-16 rejection is rule-valid: SPY closed at `739.95` against a 20-session SMA of `757.695`.

### Candidate-generation audit

212 of the 233 regime-positive sessions produced at least one eligible ETF candidate, so the candidate rules rarely suppress trading when the regime allows it. The weak link is instrument selection, not the gates: both the ETF rotation and the catalysts pick trades that underperform the index over identical holding windows.

### Head-to-head comparison (2026-04-01 to 2026-11-16 holdout)

| Series | Signals | Total return | Max drawdown | Turnover | Avg exposure | Sharpe (descriptive) |
|---|---:|---:|---:|---:|---:|---:|
| `momentum-v1` | 10 | +2.50% | 11.68% | 19.92 | 62.26% | 0.38 |
| `sec-earnings-relative-momentum-v1` | 13 | -1.25% | 2.57% | 2.59 | 4.49% | -0.94 |
| `news-catalyst-v1` | 7 | +1.56% | 11.03% | 45.91% | 0.27 |
| SPY buy-and-hold | 1 | +13.14% | 5.92% | 0.88 | 100% | 1.47 |
| QQQ buy-and-hold | 1 | +13.78% | 14.82% | 1.00 | 100% | — |
| Cash | 0 | 0.00% | 0.00% | 0 | 0% | — |

Development window (before 2026-04-01): `momentum-v1` `-2.84%`, catalyst `-2.41%`, SPY `+5.32%`, QQQ `+4.68%`.

Because exposure differs, the decisive comparison is same-notional: apply each strategy's trade dates, direction and notional to SPY with 2 bps per side.

| Strategy | Dev actual | Dev matched SPY | Holdout actual | Holdout matched SPY |
|---|---:|---:|---:|---:|
| `momentum-v1` | -2.84% | -1.36% | +2.50% | +6.07% |
| `sec-earnings-relative-momentum-v1` | -2.41% | -0.74% | -1.25% | +1.33% |
| `news-catalyst-v1` | — | — | +1.56% | +9.12% |

Every strategy loses to simply holding SPY over its own deployment dates in both windows. Selection destroyed value; the positive holdout return of `momentum-v1` is mostly index beta at 62% exposure.

### Decision

No strategy in this study has defensible evidence of alpha. This conclusion is historical: on 18 November 2026 the retired momentum and catalyst rules were replaced by `spy-directional`, which is now the only registered active strategy. The catalyst alternatives remain undeployed. The system still takes no position unless the frozen `spy-directional` rules select one, which reflects the rubric's preference for demonstrable risk control over manufactured activity.

Weaknesses that would need to be resolved before deployment: 7–13 holdout trades, overlapping regime windows, a single 17-month ETF history, adjusted-bar dividend treatment, one fixed dev/holdout split with no multiple-testing correction, and no cost-sensitivity grid. Any future attempt must use a pre-registered hypothesis on data not used here, not further tuning against this holdout.

## Moomoo-signal candidate review (18 November 2026)

Question: can Moomoo's candlestick-pattern, technical-polarity or capital-flow data materially improve `momentum-v1`? The frozen protocol is `evidence/research/moomoo-tech-audit-2026-11-18/protocol.json`; no deployed rule, RiskGate limit or order permission was changed.

### Candidate `moomoo-oversold-reversal-v1` (research only)

Universe: `AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, AVGO, JPM, XOM`. At a completed close, all of:

1. `SPY` close > 20-session SMA.
2. Stock close > 50-session SMA.
3. Moomoo `RSI_6` polarity is `OVER_SOLD` or `SEVERELY_OVER_SOLD`.
4. Moomoo daily `kline-shape.direction == BULLISH` (code non-zero).
5. Volume >= 1.2x the prior-20-session mean.
6. Prior-20-session mean dollar volume >= USD 100m.

Entry next open; 10% of equity per position; at most three concurrent positions (30% gross); no leverage or shorting; 2 bps per side. Exit next open after ten sessions, after `RSI_6` becomes overbought, or after a close below the 50-SMA. Ranking by 20-day dollar volume, then alphabetically. No news signal was used because no verified point-in-time catalyst feed is available.

### Capability and evidence findings

- `kline-shape` and `indicator-polarity` are **current-snapshot only**. Neither accepts an as-of date, so a historical signal series cannot be reconstructed without inventing provider logic.
- At the 2026-11-17 close, **0 of 12** symbols had a non-`NONE` candlestick pattern. `ktype=2` and `9` both returned `NONE`; `ktype=1` is invalid. The entry rule therefore produced zero qualified names. Removing the pattern gate after seeing this would be a post-hoc protocol change, not a valid result.
- `indicator-polarity` returned 15 named indicators with an `update_time` of 16:00 ET. `RSI_6` was oversold for MSFT, NVDA, GOOGL and JPM, but the regime was negative and no pattern existed. RSI_6 is also largely a nonlinear restatement of recent price movement, so it does not establish independent information beyond the existing momentum input.
- Provider `indicator-backtest` statistics are not auditable: the window, horizon and methodology are undisclosed. For AAPL `RSI_6/OVER_SOLD` it reports 50 occurrences, 54% up and average change `+0.038%`; across 15 indicators samples were 4–55 and `probability_up` ranged 41.7%–95%. These are not point-in-time backtests and were not used as evidence.
- `POST .../unusual/technical` returned HTTP 403 (`-12006`) with the current authorization and was not used.
- Capital-flow history is genuinely historical, but it did not provide positive independent confirmation. Across 4,730 overlapping 10-stock observations (473 unique dates, 500 sessions), 5-day normalized main inflow had Pearson correlation `0.255` with the past 5-session return, `0.16` with 20-session momentum and `-0.034` with the next 5-session return. Positive-flow observations averaged `+0.177%` forward versus `+0.523%` for non-positive flow. Overlapping windows make these descriptive only, but they do not support adding the signal.
- **RiskGate incompatibility:** the candidate stocks are outside the deterministic allowlist `{SPY, QQQ, IWM}`. Any deployment would require an owner-approved widening; none was requested or made.
- **Forward observation:** the first timestamped record (`2026-11-17`, regime false, zero qualified) is in `evidence/research/moomoo-signal-observation/observations.jsonl`. It is a capability observation, not a performance result; one snapshot cannot establish a base rate.

### Independent review

Two independent AI reviews were run against the frozen protocol. The research reviewer returned **REJECT** for capital use: the pattern gate has no verified positive case, the provider labels are opaque, and the hypothesis is a clustered short-term reversal with an effective sample of roughly one day. The risk reviewer returned **SAFE_FOR_RESEARCH_ONLY** and required deterministic selection persistence, session/provider timestamp checks and a protocol hash before further records; those checks are implemented in the observer, and v1 was not silently edited. No AI output can override the deterministic rules or RiskGate.

### Recommendation

**HISTORICAL recommendation:** this review preceded the 18 November pivot from `momentum-v1`. The then-successor `spy-directional` used the now-retired fixed-size policy and return-plus-SMA50 direction rule; those are not current v2 behaviour. The candidate was outside the then-allowlist `{SPY, QQQ, IWM}` and remains undeployed. Its defining entry condition produced zero signals on the only observed close, and capital flow did not add positive forward information. The observer script was removed during the 18 November cleanup; `evidence/research/moomoo-signal-observation/` remains a historical capability log, not alpha evidence. Current v2 controls and prepared SPY/SH-only execution defaults are specified above; retired policy cannot be reactivated.

Implementation effort if this were ever revisited: low for a read-only observer, high for deployment because it requires an owner-approved universe change, an authorized write token and a separately verified broker lifecycle. The execution permission and broker-lifecycle blockers are unchanged.

## HISTORICAL unit/integration coverage before the mandate change

Checked items record the prior suite only; they do not establish that the new v2-only/per-order-approval changes pass. Current verification requirements follow below.

- [x] Wrong or unverified account cannot submit.
- [x] Live account, other paper account and market-only selection are rejected.
- [x] First paper order without durable owner approval is rejected before the broker.
- [x] Oversized proposed order rejected *before broker adapter is called*.
- [x] Stale quote, missing quote or missing market-data timestamp leads to abstention.
- [x] Missing 20-session history leads to abstention.
- [x] Insufficient buying power or ETF outside allowlist rejected.
- [x] Maximum three open positions blocks a fourth.
- [x] Persistent kill switch survives restart.
- [x] Daily drawdown 2% threshold blocks new buying.
- [x] Duplicate request key creates at most one simulated order.
- [x] Ambiguous broker timeout recorded `UNKNOWN` and not retried blindly.
- [x] Partial fills reflected accurately, with pending remainder accounted for.
- [x] Broker/ledger position mismatch or unreadable account halts order writes.
- [x] Executed fills are never inferred from an acknowledgement alone.
- [x] Illegal order state transitions are rejected by the ledger.
- [x] Read-only adapter selects the exact competition account among paper accounts, rejects other paper/live accounts, and never prints the full account id.
- [x] Malformed provider responses, short positions/orders, inconsistent totals, unknown order states and stale observations fail closed.
- [x] Adapter exposes only four read tools, rejects every order-writing tool before the caller, and cannot submit or read broker orders.
- [x] Cash-only sizing ignores `max_power_long`; a 150,000 USD request is rejected against 100,000 USD cash even when margin buying power is 200,000 USD.
- [x] Daily equity baseline and peak persist across adapter restarts.
- [x] Mock risk rejection is clearly separated from real paper trading results.
- [x] Qoder custom-tool schemas reject malformed, oversized and unexpected inputs.
- [x] A modified proposal cannot pass the pinned research binding.
- [x] The Qoder runner sends one result per tool call, does not retry ambiguous delivery and captures no Vault/resources.
- [x] The ETF baseline caps entry notional at 10%, executes after its signal and exercises the monthly exit path.
- [x] Fresh quote/market-state preflight accepts only the regular session and fails closed on stale, future, suspended, wrong-symbol and malformed data.
- [x] POST-for-read quote paths are allowlisted; order paths are refused and refresh failure is fatal.
- [x] Correlation tags are bounded and deterministic; ambiguous broker matches are rejected rather than guessed.
- [x] The disabled order adapter matches the documented payload and refuses both enabled and disabled submission attempts.
- [x] Provider order statuses map strictly, including partial, filled, cancelled and rejected variants.
- [x] Accepted-but-timed-out submissions persist `UNKNOWN`, block new submissions, reconcile from today/history/positions and are never retried automatically.
- [x] Leveraged instruments are rejected by default (`R015`) and checked on effective exposure only when explicitly opted in.
- [x] Unexpected broker response objects or mismatched keys become `UNKNOWN` instead of fills.
- [x] Tier calculation maps SPY return/trend/volatility to the documented risk-v3 exposure tiers — `<1.5%` → 0%, `1.5–3%` → 10%, `3–5%` → 25%/40% trend-confirmed, `5–8%` → 40%, `>= 8%` → 40% capped — with the `40%` CASH volatility gate and no leverage path.
- [x] ETF selection follows the target: `f > 0` → SPY, `f < 0` → SH, one directional position at a time; UPRO/SPXU are outside the universe and rejected by default-deny validation.
- [x] Sizing spends `|target|` of equity as cash and floors to whole shares at the bar close.
- [x] HISTORICAL suite: risk-v2 floor (`R016`), signed-effective ceiling (`R017`) and target consistency (`R018`), plus then-retained risk-v1 regressions. This records prior coverage, not a current selectable v1 policy or verification of the new supervised floor handling.
- [x] Resize rules are deterministic: tier moves resize only on `>= 1` share and `>= 5%` relative deltas; direction flips SELL first.
- [x] The risk monitor's due-window resolution, drawdown, signed/unsigned exposure, holding-duration, open-order and ambiguous-submission checks, and its kill-switch policy (drawdown or pre-close unresolved only) are tested.
- [x] The owner-operable kill-switch CLI requires explicit confirmation to engage or release and writes audit events; the persistent switch blocks new orders without liquidating holdings.
- [x] risk-v3 focused coverage: WEAK/MODERATE/STRONG sizing (10%/25%/40% and the trend-confirmed 40% MODERATE), CASH at 0%, the 40% cap, UPRO/SPXU rejection (including attempted leverage permission), SPY/SH reversals after confirmed liquidation, preserved controls, stale-policy approval rejection and no submission from previews (suite green 20 November 2026, 558 backend tests + 19 frontend tests).

**HISTORICAL verification record:** the prior `backend/tests` suite recorded 400 tests on 19 November 2026, including the then-dual-policy implementation. That count is not a new result for the current mandate. Initial real REST reads observed the exact competition account at 100,000 USD with no positions/orders; later QQQ diagnostic BUY `3115842` and SELL `3115920` filled and reconciled on 18 November. The historical Qoder run `qoder-328aefff-7dde-4a98-ac76-99b3e0e33728` recorded the old SH proposal and rejection, not a v2 order. Provider clock skew ≤5s remains tolerated; larger skew fails closed, and stale quotes report age separately. MCP adapter results remain fixtures. Use mocks for negative tests, not unsafe competition-account experiments.

**Current backend acceptance checks:** verified by focused risk, research, trading-flow and supervised CLI tests on 20 November after the risk-v3 simplification; overall suite results are recorded in `docs/evidence.md`.

- [x] Risk-v1 cannot be selected/reactivated; active research and execution are risk-v3 only; pre-simplification risk-v2 decisions remain distinguishable as HISTORICAL.
- [x] EVERY supervised BUY/SELL requires exact-proposal/key approval, including after prior fills; owner approval is independent of the 30-second risk TTL; stale-policy approvals cannot authorise an order and superseding preserves the historical row.
- [x] Execution scope is SPY/SH only; UPRO/SPXU are rejected by `R002`/`R015` even when a leverage permission is attempted, and the supervised path skips the floor.
- [x] Signed-effective 40% ceiling, ±5pp target tolerance, one-position gate, 2% drawdown, US$5 buffer and 300s/60s freshness remain enforced.
- [x] `--proposal-file` preserves research timestamps/evidence/target and rejects mismatched required flags; supervised previews report per-rule states and current/post signed exposure without submission.
