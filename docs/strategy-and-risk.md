# Strategy and risk specification

**Version:** `momentum-v1` draft. The rules below are a testable baseline, not a proven profitable strategy. Freeze parameters before evaluating competition-period returns; record every change and its reason.

## Thesis and instrument universe

Long-only regime-aware ETF momentum, initially limited to `SPY`, `QQQ`, `IWM` **if** the competition's allowed instruments and available market data confirm eligibility.

Thesis: stronger recent momentum during a favourable broad-market trend may persist, but sitting in cash during a weak regime can reduce risk. This hypothesis may fail; evidence must include losses, abstentions and a benchmark.

## Initial deterministic signal specification (to ratify before first trade)

- Source: timestamped, broker-approved adjusted daily close prices, as available without look-ahead; if adjustment semantics differ, document them and avoid mixing.
- Decision cadence: at most one scheduled daily evaluation after sufficient price data is available, in a supported exchange session; validate the actual schedule and market hours.
- Broad-market regime: `SPY last fully completed daily close > SPY trailing 20-session simple moving average` computed from completed sessions only.
- Candidate momentum: 5-session price return of each whitelisted ETF; only consider candidates with return > 0 and price above their own trailing 20-session SMA.
- Selection: choose highest eligible 5-session return, deterministic ticker alphabetical tie-break.
- Position action: if no candidate or regime negative => `NO_TRADE` for new entries. Evaluate already-held position against the exit rules; never assume no-trade equals liquidate.
- Exit: sell a held instrument when its completed-day close falls below its own 20-session SMA, or as needed by explicitly authorised risk de-risking policy. Document any other exits as a new version.
- Model's role: explain evidence and uncertainties, **not** replace mathematical rules or choose an unapproved ticker.
- Warmup: minimum 21 fully completed trading sessions needed; without sufficient history, abstain.
- Initial execution assumption for the local mock: whole-share `MARKET` orders with `DAY` time-in-force during the regular exchange session. Actual provider support remains unverified.
- Initial freshness policy: quotes no older than 300 seconds and account snapshots no older than 60 seconds; future timestamps are rejected.

**Known limitation:** This baseline may generate very few signals over a 12-day period. If the team wants more trades, revise through a documented predeclared rule change, not by selectively overriding controls to improve reported returns.

## Preliminary hard constraints

| Rule ID | Starting limit | On breach |
|---|---|---|
| R001 | Account must be the exact verified competition paper account (masked id + fingerprint, simulated source) | Reject and disable order writes |
| R002 | Symbols restricted to validated allowlist | Reject |
| R003 | Long-only, cash-only; no options, short selling or leverage | Reject |
| R004 | Per-instrument exposure <= 10% of equity (post-order) | Reduce/reject by deterministic sizing policy |
| R005 | Total gross invested exposure <= 30% equity | Reduce/reject by deterministic sizing policy |
| R006 | Daily equity drawdown >= 2% from the trading day's starting equity | Pause new buying; leave liquidation to a separate documented policy |
| R007 | Quote / account snapshot missing, stale, invalid or contradictory | Reject/abstain |
| R008 | Insufficient unlevered cash after fees/buffer | Reject |
| R009 | Reconciliation mismatch, unknown order or unreadable broker state | Halt new submissions |
| R010 | Persistent kill switch on, circuit breaker open or writes disabled | Reject all submissions |
| R011 | Duplicate run/approved proposal/order key | No duplicate submit |
| R012 | Exchange/session constraints or ineligible order type | Reject |
| R013 | Post-order open positions > 3 distinct instruments | Reject new buying |
| R014 | First paper order without explicit, durable owner approval | Reject before broker call |

Limits are conservative **initial choices**, not necessarily optimal. No LLM, agent administrator or dashboard button may silently bypass them. Changes must be versioned and audited; actual competition rules take precedence.

**Cash-only note:** the competition US paper account may be margin-type. R008 uses `min(cash, buying_power) - buffer`, so broker margin is never used even when reported buying power exceeds cash.

### How quantity is computed

1. Resolve the exact competition account by masked id + SHA-256 fingerprint; reject live, other-paper and market-only matches.
2. Get broker-confirmed equity, day-start equity, current holdings, pending orders and buying power.
3. Compute available headroom under `R004`, `R005` and `R013` using **post-order** positions and pending exposure.
4. Apply strategy's smaller preferred position size if defined.
5. Subtract conservative transaction-cost/buying-power buffer if available.
6. Floor to valid integer share quantity and verify minimum/lot size constraints.
7. If `< 1` valid share or the resulting trade is below applicable minimum, abstain with reason.
8. Bind approval to current account snapshot; expire and recompute if conditions change.

The first paper order additionally requires a durable owner approval tied to its `client_order_key` (`R014`). The command records approval only; it never submits an order.

## Fail-closed order flow

`proposal → schema validation → snapshot refresh → risk policy → durable approval and idempotency key → paper write → broker status refresh → reconciliation → event + report`

If the broker call times out, status is **UNKNOWN**. Do not send a replacement order until a status query and account reconciliation rule out the original. Acknowledgement does not equal fill.

### Execution-time preflight

Before any order can be submitted, the executor must obtain a fresh quote for the exact symbol (no older than 300 seconds, not future-dated, positive price, normal trading status, not suspended) and confirm the regular US session from the provider's market-state response. Only `AFTERNOON` is accepted as regular hours; the provider defines it as 09:30–16:00 ET. A closed session, stale quote, malformed market state or unreadable account snapshot blocks execution before the broker adapter is reached.

### UNKNOWN submission handling

A timeout or malformed broker response is persisted as `UNKNOWN` before any further action. While any `UNKNOWN` submission exists, all new submissions are rejected (`R009`). Reconciliation queries three broker sources — today's orders, order history and the account snapshot/positions — and requires the snapshot's paper environment and account fingerprint to match the submission. It then matches exactly one broker order by the correlation tag carried in the documented `text` remark and validates symbol, side and quantity against the local request. Zero matches stays `UNKNOWN` (no match); more than one match is ambiguous and also stays `UNKNOWN`; an account mismatch stops reconciliation. Neither case retries the order. A unique match is written to the ledger only if the provider status transition is legal. The remark is a correlation aid, not a broker-enforced idempotency key.

The order path remains a disabled prototype: `ORDER_WRITES_ENABLED=false`, the documented simulated-order transport is inactive and not runtime-wired, and the operator preview (`moomoo-preview-order`) evaluates the deterministic gate and prints the planned payload, safety checks and `submission_performed: false`. No order has been sent.

## Pausing vs killing

- `PAUSED`: no new order submissions; continue read-only sync, audit and reporting.
- `HALTED`: persistent safety interlock; manual review and preflight required to resume. Display prominent warning.
- `KILL`: operator-triggered persistent stop of new writes. If cancellation is supported, separately offer documented authorised cancellation of pending orders.
- None of these states implicitly means existing holdings have been liquidated.

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

`etf-trend-baseline-v1` is a deliberately simple, low-turnover comparator. It is not registered as an executable strategy and has no proposal builder or order path.

- At each completed month-end, hold `SPY` only if its close is above its 200-session SMA; otherwise hold cash.
- Execute a changed signal at the next session open. Maximum `10%` of equity at entry, preserving `R004`; 2 bps per side; fractional shares.
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

No strategy in this study has defensible evidence of alpha. The deterministic momentum rules stay frozen and the system remains in `NO_TRADE` unless those rules say otherwise; the catalyst alternatives are not deployed. This is a deliberate choice, not a forced trade, and it respects the rubric's preference for demonstrable risk control over manufactured activity.

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

Retain `momentum-v1` unchanged and keep `NO_TRADE` (SPY closed `732.44` against a 20-session SMA of `755.86` on 17 November 2026); do not deploy the Moomoo-signal candidate, do not widen the RiskGate allowlist and do not continue it as a capital-bearing paper strategy. The candidate has no historical validation, its defining entry condition produced zero signals on the only observed close, and the one historically auditable Moomoo signal (capital flow) did not add positive forward information. The observer may remain a read-only capability log if pattern availability is worth tracking, but it is not evidence of alpha.

Implementation effort if this were ever revisited: low for the read-only observer (already present), high for deployment because it requires an owner-approved universe change, an authorized write token and a separately verified broker lifecycle. The execution permission and broker-lifecycle blockers are unchanged.

## Required unit/integration tests

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
- [x] Unexpected broker response objects or mismatched keys become `UNKNOWN` instead of fills.

Implemented in `backend/tests` (**284 tests on 18 November 2026**, including REST auth/read, execution-scope validation, quote/session execution preflight, disabled order-transport success/partial/rejection/timeout/duplicate/`UNKNOWN` mocks, order-correlation/reconciliation, Qoder runner/tool, ETF baseline, scheduler catch-up/lock/interruption recovery, clock-skew handling and read-only dashboard API tests). The REST adapter also completed real read-only provider calls to the competition account: exact identity, 100,000 USD cash/equity, zero positions and orders, `reconciled=true`. A genuine current-market read-only Qoder run during the US regular session and a genuine Task Scheduler-triggered catch-up each recorded `NO_TRADE` (negative broad-market regime) with no order submitted. Provider timestamps within 5 seconds of local time are accepted as clock skew; larger skew fails closed, and stale quotes separately report their age. MCP adapter results remain provider-shaped fixtures. No Python transport connects the MCP adapter to cloud data, and no order was placed. Use mock responses for negative/failure-injection tests; avoid deliberately compromising the competition paper account.
