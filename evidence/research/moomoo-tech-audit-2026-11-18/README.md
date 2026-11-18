# Moomoo technical-signal audit — 18 November 2026

Read-only capability audit and prospective candidate record. No order endpoint was contacted, `ORDER_WRITES_ENABLED=false`, and the token has no `trade:read` or `trade:write` scope.

## Artifacts

| File | Meaning |
|---|---|
| `protocol.json` | Frozen rules and evaluation plan (`moomoo-oversold-reversal-v1`), frozen before returns were examined. |
| `snapshot-2026-11-17.json` | Raw kline-shape and indicator-polarity responses for 10 stocks plus SPY/QQQ at the 17 November close. |
| `kline-shape-ktype-probe.json` | ktype 1/2/9 check; 1 is rejected, 2/9 returned `NONE` for the tested names. |
| `indicator-backtest-AAPL-all.json` | Provider statistics for indicator IDs 1–15; windows and methodology are not disclosed. |
| `flow/<symbol>.json` | 500 daily capital-flow observations, 2024-11-19 to 2026-11-17. |
| `bars/<symbol>.json` | 500 daily OHLCV bars for the same dates, fetched in two date ranges. |
| `analysis.json` | Snapshot counts, provider-stat ranges and descriptive capital-flow correlations. |
| `../moomoo-signal-observation/observations.jsonl` | Append-only forward observations; first record is 2026-11-17, regime false, zero qualified. |

## Key observations

- 0 of 12 symbols had a non-`NONE` daily candlestick pattern at the 2026-11-17 close.
- `indicator-polarity` is a single current snapshot updated at 16:00 ET; it has no as-of parameter.
- `indicator-backtest` is provider-computed with an undisclosed window; it is not a point-in-time backtest.
- The `POST .../unusual/technical` probe returned HTTP 403 (`-12006`) and was not retried.
- Capital-flow history is genuinely historical, but 5-day main inflow had Pearson correlation `-0.034` with the next 5-session return across 4,730 overlapping observations. This is descriptive, not a strategy result.
- No historical performance is claimed for the candidate. The first observer record is a capability observation, not a return.

## Limitations

- Overlapping 5-session windows; effective sample is far below 4,730 independent observations.
- One pattern snapshot cannot establish a base rate or rule out provider-side sparsity.
- Adjusted bars (`autype=1`) and daily flows may not reconcile exactly to cash dividends or corporate actions.
- The observer is manual unless separately scheduled; the local 16:20 ET daemon missed its 17 November fire.
