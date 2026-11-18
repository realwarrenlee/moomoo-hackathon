# Vibe-Trading proof of concept

**PAPER / HISTORICAL RESEARCH — NO BROKER, APPROVAL OR ORDER**

## Result

| Metric | Vibe GlobalEquityEngine | MooTrade simulator |
|---|---:|---:|
| Total return | 0.0895% | 0.0895% |
| Final value | $100089.46 | $100089.46 |
| Max drawdown | -1.2156% | 1.2156% |
| Sharpe (descriptive) | 0.0573 | 0.0573 |
| Sessions | 349 | 349 |
| Round-trip trades | 23 | 23 |

- Maximum common-session equity difference: **$0.000000000058** over 349 sessions. The two engines hold identical shares and produce the same equity curve.
- Terminal values are identical to floating-point precision: Vibe `$100089.46` vs MooTrade `$100089.46`. No position was open at the end of this run.
- Both engines now compute total return on the $100,000 initial equity, and MooTrade's curve includes that initial value. The metric-base discrepancy found by the original POC was corrected in `backend/app/research/evaluate.py`.

## Data verification

- 370 provider sessions; Moomoo US calendar returned 370 sessions; exact match: **True**.
- All timestamps are midnight America/New_York: **True**.
- Shared calendar across SPY/QQQ/IWM: **True**; no duplicate sessions: **True**; no weekend bars: **True**.
- OHLC invariants and Vibe `validate_ohlc(strategy='raise')`: **True**.
- **Price-basis defect found:** the fixture metadata says `autype=1`, but its 2025-05-29 close (`590.05`) matches `history-kline autype=0` raw (`590.05`), not `autype=1` forward-adjusted (`580.422236757`).
- The POC's engine comparison remains valid because both engines consumed the same fixture bars; the fixture is not valid evidence of forward-adjusted returns.

## What was actually used

- Vibe `GlobalEquityEngine` / `BaseEngine.run_backtest`, `_align`, `validate_ohlc`, `calc_metrics`, run-card and artifacts; not the Vibe agent runner.
- The full runner is blocked in this environment by missing `fastmcp` and a module-level `yfinance` import in `backtest.benchmark`.
- The only offline substitution is the external benchmark resolver, which returns none; no network or market-data call is made by Vibe.
- The POC overrides US fractional sizing to whole shares and forces no daily resizing.

## Verdict

Vibe's execution engine can consume the Moomoo fixture and reproduce the frozen momentum-v1 cash/exposure path exactly (equity difference below $1e-10). The POC also found a MooTrade metric-base defect, now corrected, and a stale price-basis label in the existing fixture. Vibe is usable as a research engine with adaptation, but this single POC does not justify replacing MooTrade's research path by itself.

Artifacts: `results.json`, `vibe-run/` (Vibe artifacts and run card), `vibe-run/artifacts/equity.csv`, `history-probe.json`, `autype-probe.json`.
