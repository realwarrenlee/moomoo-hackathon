# Frozen protocol evaluation — volume-confirmed relative strength

**PAPER / HISTORICAL RESEARCH — NO BROKER, APPROVAL OR ORDER**

Protocol: `volume-confirmed-relative-strength-v1`, frozen at `evidence/research/stock-selection-prereg-2026-11-18/protocol.json`. Window: 2016-01-04 to 2024-12-31. No 2025-2026 bar was loaded for this protocol; the earlier ETF holdout was not reused.

## Verdict

- Strategy total return: **36.82%**; CAGR **3.55%**; max drawdown **-5.29%**.
- Same-schedule exposure-matched SPY: **20.47%**; equal-weight fixed universe at 30% gross: **107.48%**; constant 30% SPY: **47.89%**; cash: **0.00%**.
- Beat exposure-matched SPY: **True**; beat equal-weight universe: **False**.
- Pre-registered rejection rule triggered: **True** (top-three episode concentration: **False**; fewer than 30 completed episodes: **False**).

This is one pre-registered run, not a parameter search. It is historical development evidence only; it is not deployment approval and does not authorise any allowlist, RiskGate or order change.

## Data verification

- 21 symbols; 2516 US sessions (2015-01-02 to 2024-12-31).
- No bar on or after 2025-01-01: **True**.
- All symbols share the provider calendar: **True**; no duplicates: **True**; no weekends: **True**; OHLC valid: **True**.
- Price basis: Moomoo `history-kline` `autype=1` forward-adjusted OHLC; volume is the provider daily volume. No adjustment factor is reconstructed independently.
- Largest absolute one-session close move across all symbols: **52.3%** (AMD, 2016-04-22, close 2.62 to 3.99, volume 14.3x the prior session). This is consistent with a real event rather than a split-scale break, but no independent price source was cross-checked.
- Data errors: **0**.

## Protocol implementation checks

- Weekly schedule: **470** decision weeks, first execution 2016-01-04, last execution 2024-12-30.
- Target constraints: max names **3**, max gross **0.30**, issues **0**.
- Independent reference selection on first/middle/last weeks: **True**.
- Look-ahead test (truncate and multiply all post-2020-06-30 bars): **True** across 235 weeks.

## Strategy result

| Metric | Value |
|---|---:|
| Final value | $136815.38 |
| Total return | 36.82% |
| CAGR | 3.55% |
| Annualized volatility | 4.91% |
| Sharpe (daily, 252) | 0.735 |
| Maximum drawdown | -5.29% |
| Average gross exposure | 14.28% |
| Maximum gross exposure | 32.45% |
| Days above 30% gross (intraweek drift) | 291 |
| Average names held | 1.43 |
| Weeks invested / cash | 305 / 165 |
| Average weekly one-way turnover | 10.90% |
| Completed holding episodes | 514 |
| Fill-episode P&L vs equity P&L | $0.000000 difference |
| Hit rate | 52.5% |
| Average holding period | 6.3 sessions |
| Top three episodes' share of net P&L | 27.4% |

## Benchmark comparison

| Run | Total return | CAGR | Volatility | Max drawdown | Average gross |
|---|---:|---:|---:|---:|---:|
| Strategy | 36.82% | 3.55% | 4.91% | -5.29% | 14.28% |
| SPY at strategy weekly gross | 20.47% | 2.09% | 2.43% | -3.09% | 14.24% |
| SPY constant 30% | 47.89% | 4.45% | 5.32% | -11.25% | 29.89% |
| Equal-weight 20 stocks, 30% gross | 107.48% | 8.46% | 6.08% | -9.69% | 29.17% |
| Cash | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |

- Excess vs same-schedule exposure-matched SPY: **16.34%**.
- Excess vs equal-weight fixed universe: **-70.67%**.
- Risk-adjusted, the strategy's Sharpe (**0.735**) is below exposure-matched SPY (**0.867**), constant 30% SPY (**0.846**) and equal-weight (**1.367**). The strategy wins only on raw return versus exposure-matched SPY, not per unit of risk.
- The equal-weight comparator averaged **29.17%** gross versus the strategy's **14.28%**, so the raw-return rejection is partly an exposure difference. The frozen protocol specified this 30%-gross comparator; no post-hoc exposure-matched equal-weight variant was run.

## Year-by-year returns

| Year | Strategy | Exposure-matched SPY | Constant 30% SPY | Equal-weight 30% |
|---|---:|---:|---:|---:|
| 2016 | 0.48% | 0.83% | 3.93% | 9.10% |
| 2017 | 1.10% | 2.44% | 6.09% | 10.43% |
| 2018 | 5.18% | -0.34% | -1.05% | 3.05% |
| 2019 | -1.16% | 1.06% | 8.63% | 11.90% |
| 2020 | 12.40% | 2.53% | 6.14% | 14.42% |
| 2021 | 8.40% | 5.49% | 8.00% | 10.17% |
| 2022 | -1.00% | -1.53% | -5.35% | -6.52% |
| 2023 | 6.43% | 3.03% | 7.41% | 14.07% |
| 2024 | 0.90% | 5.53% | 7.07% | 11.10% |

### Selection by year (attributed to execution year)

| Year | Weeks | Zero-name weeks | Selected-name slots |
|---|---:|---:|---:|
| 2016 | 52 | 16 | 76 |
| 2017 | 52 | 10 | 96 |
| 2018 | 53 | 19 | 74 |
| 2019 | 52 | 17 | 68 |
| 2020 | 52 | 18 | 84 |
| 2021 | 52 | 8 | 98 |
| 2022 | 52 | 46 | 13 |
| 2023 | 52 | 14 | 82 |
| 2024 | 53 | 17 | 81 |

## Selection activity

- Weeks with 0 / 1 / 2 / 3 names: 165 / 87 / 69 / 149.
- SPY regime false in **84** weeks; zero-name weeks **165**.
- Average eligible names per week: 2.0; maximum 14.
- Most selected symbols: AMD (62), NVDA (55), AVGO (49), TSLA (48), AAPL (41), NFLX (41), AMZN (38), GOOGL (32).

## Interpretation assumptions

- 10% per name is 10% of current portfolio equity; the weekly rebalance resets selected names to 10% and sells names no longer selected. This is the target-rebalance reading of the frozen protocol.
- Initial capital is $100,000, whole shares, cash only, no leverage, no shorting.
- The 30% gross limit is a weekly rebalance target, not an intraweek stop; price drift can leave close-of-day gross slightly above 30%, and those days are counted in the result.
- Costs are 2 bps per side via Vibe's US slippage setting; US commission is zero.
- The 2015-12-31 weekly signal is evaluated for the first 2016-01-04 execution; it selected no names because the SPY regime was false. 2015 is warmup only.
- 2024-12-31 is the last bar. Vibe force-closes any open position at that bar's close with slippage (`end_of_backtest`); the protocol has no intraweek stop.
- The final week's signal (2024-12-31) has no execution inside the window and is not used.
- The frozen rule's "depends on a handful of trades" is operationalised as: the top three completed holding episodes account for at least 100% of positive net P&L, or fewer than 30 completed episodes exist. Both diagnostics are reported; this is an evaluator check, not a tuned parameter.

## Limitations

- Fixed 20-stock universe declared before evaluation: survivorship and selection bias; it is not point-in-time index membership.
- Forward-adjusted OHLC uses adjustment factors known only after the fact; relative returns and SMAs are largely invariant to multiplicative adjustment, but this is not a fully point-in-time corporate-action reconstruction.
- Volume is raw provider volume. A stock split inside the 25-session volume window can create a false volume expansion (AAPL, NVDA, TSLA, AMZN, GOOGL and AVGO all split in this period). No split-adjusted volume was fabricated.
- No delisted or halted names are present; large-cap coverage was complete.
- Only one run was made; no parameter grid, threshold search or holdout reuse.
- Vibe's auxiliary `risk_xray_*` fields and some internal counters did not correspond to the exposure-scaled portfolio equity or to `fills.jsonl`; they were not used. All reported metrics are recomputed from `equity.csv` and reconcile to fill episodes within $2.4e-10.
- Vibe's terminal liquidation may differ from a mark-to-market ending and is applied to every run.
- The full Vibe runner is not used: fastmcp is missing and `backtest.benchmark` imports yfinance. The real engine is invoked in-process with only the external benchmark resolver stubbed.

## Evidence

- `protocol-data/daily-bars-2015-2024.json` — 21-symbol OHLCV, provider metadata, calendar and request log.
- `protocol-runs/strategy/artifacts/` and `protocol-runs/*/artifacts/` — Vibe equity, fills, trades, positions, targets and run cards for every run.
- `protocol-results.json` — metrics, selections, validation and comparison.
