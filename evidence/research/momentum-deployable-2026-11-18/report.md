# Momentum-v1 deployable-limit evaluation

**PAPER / HISTORICAL RESEARCH — NO BROKER SNAPSHOT, APPROVAL OR ORDER**

- Strategy: frozen `momentum-v1`; no rule or parameter change.
- Period: `2025-06-27` to `2026-11-16`; 349 evaluated sessions from a 370-session fixture.
- Sizing: 10.0% of equity per position, 30.0% gross cap, at most 3 positions, whole shares, cash only.
- Execution/cost: next session open, 2 bps per side; no leverage or shorting.
- This is the same fixture and frozen rules as the earlier signal-quality study; it is **not** new out-of-sample evidence.

## Results

| Series | Total return | CAGR | Ann. vol | Sharpe | Max drawdown | Avg exposure | Max exposure | Entries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| momentum-v1, 10% / 30% limits, whole shares | 0.09% | 0.06% | 1.27% | 0.0573 | 1.22% | 6.62% | 11.25% | 23 |
| SPY hold, 10% | 2.07% | 1.49% | 1.47% | 1.0098 | 1.02% | 11.29% | 12.37% | 1 |
| SPY hold, 6.62% entry (approximate exposure match) | 1.37% | 0.99% | 0.98% | 1.0054 | 0.68% | 7.51% | 8.27% | 1 |
| SPY hold on strategy entry/exit sessions, 10% | 0.43% | 0.31% | 0.98% | 0.3233 | 0.97% | 6.53% | 11.24% | 23 |
| Cash | 0.00% | 0.00% | 0.00% | n/a | 0.00% | 0.00% | 0.00% | 0 |

## Difference from the earlier 100%-notional signal-quality study

| Metric | Prior 100%-notional study | Deployable 10% / 30% study | Difference |
|---|---:|---:|---:|
| Total return | -0.41% | 0.09% | +0.50 pp |
| Max drawdown | 11.68% | 1.22% | -10.46 pp |
| Average exposure | 65.71% | 6.62% | -59.09 pp |

The prior study invested all available cash in one ETF and reached 100% exposure; this study caps each entry near 10% and leaves the remainder in cash. The return and drawdown differences are therefore mostly a sizing effect, not a new signal. The 30% gross cap and three-position limit never bind because the frozen strategy holds at most one ETF.

## Exposure-matched comparisons

- A constant 10% SPY holding returned **2.07%** with 1.02% maximum drawdown.
- A constant SPY holding entered at the strategy's average exposure (6.62%; realized 7.51%) returned **1.37%**.
- Holding SPY on the strategy's exact entry and exit sessions (realized 6.53% average exposure) returned **0.43%**.
- Deployable momentum-v1 returned **0.09%** with 6.62% average exposure. It did not beat any SPY comparator on the same dates.

## Limitations

- Same 370-bar fixture, with 349 evaluated sessions from 2025-06-27 to 2026-11-16; one market regime and 23 entries. This is not out-of-sample evidence.
- The earlier holdout window is reused only to show the effect of realistic sizing. It is not presented as a new independent test.
- Whole-share flooring and 10% entry sizing can leave small residual cash and drift above 10% at the close (observed maximum 11.25%).
- Adjusted-bar dividend treatment, taxes and corporate actions are not modelled separately.
- Historical fills, liquidity and broker state are not simulated. No order was submitted.

Artifacts: `results.json`, `equity-curves.csv`, `trades.csv`.
