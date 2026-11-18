# ETF trend baseline study

**PAPER / HISTORICAL RESEARCH — NO BROKER SNAPSHOT, APPROVAL OR ORDER**

- Baseline: `etf-trend-baseline-v1`
- Data: committed Moomoo daily bars, `2025-05-29` to `2026-11-16`
- Evaluation: `2026-04-01` to `2026-11-16`
- Rules: at each completed month-end, hold SPY only if its close exceeds its 200-session SMA; execute at the next session open; maximum 10% of equity at entry; 2 bps per side; fractional shares.

## Results

| Series | Total return | CAGR | Ann. vol | Sharpe | Max drawdown | Avg exposure | Turnover | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ETF trend baseline (10% max) | 0.26% | 0.41% | 1.37% | 0.3048 | 0.63% | 9.04% | 0.0996 | $2.00 |
| SPY hold (10%) | 1.31% | 2.09% | 1.57% | 1.3244 | 0.69% | 11.26% | 0.0986 | $2.00 |
| SPY hold (100%, reference) | 13.14% | 21.61% | 13.98% | 1.4691 | 5.92% | 100.00% | 0.8754 | $20.00 |
| Cash | 0.00% | 0.00% | 0.00% | n/a | 0.00% | 0.00% | 0.0000 | $0.00 |

## Trades

| Entry signal | Entry | Exit | Symbol | Entry notional | Return |
|---|---|---|---|---:|---:|
| 2026-04-30 | 2026-05-01 | open at end | SPY | $9998.00 | 2.57% |

The baseline returned **0.26%**, versus **1.31%** for a matched 10% SPY holding and **13.14%** for a fully invested SPY reference. It made one entry and did not exit before the data ended. The trend filter avoided most of April's decline but entered on 1 May after the recovery had begun, illustrating monthly timing lag.

## Limitations

- This is a signal-quality study with fractional shares, not a competition paper-account return. It does not prove execution, fills, buying power or account identity.
- The fixture contains 370 sessions; the 200-session warmup leaves only about eight months and seven monthly decisions. One entry cannot establish durable alpha.
- The 10% cap is enforced at entry. Mark-to-market drift can exceed it between monthly reviews (observed maximum 10.71%).
- Monthly decisions can miss fast reversals and produce a large gap between the signal close and the next-open fill.
- Corporate-action and distribution treatment depends on the pinned Moomoo adjusted bars; cash dividends and taxes are not separately modelled.
- The strategy is not registered in the order pipeline, has no proposal builder, and cannot submit orders. Any promotion requires a new reviewed version, the deterministic RiskGate, reconciliation and explicit first-order approval.
- Descriptive Sharpe is not statistically meaningful for this short sample.

Artifacts: `results.json`, `equity-curves.csv`, `trades.csv`.
