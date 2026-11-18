# Vibe-Trading research harness

**PAPER / HISTORICAL RESEARCH — NO BROKER, APPROVAL OR ORDER**

This directory preserves the pinned Vibe-Trading research harness and its
evidence. Vibe is **not** a MooTrade production dependency. Nothing here is
imported by the backend, and nothing here can submit an order.

Pinned Vibe-Trading revision:

```text
a8d815d17ec054a34dbdfc7ce8d1d9972566b709
v0.1.19-209-ga8d815d1
```

The harness uses Vibe's real `GlobalEquityEngine` in-process. The full
`python -m backtest.runner` path is not used because it requires `fastmcp`, a
`yfinance` import in `backtest.benchmark`, and a run-directory layout that this
repository does not install. The only substitution is the external benchmark
resolver, which is stubbed to return `None`; no network or market-data call is
made by Vibe. See `integration-verdict.md` for the module-level audit.

## Isolation rules

- Keep Vibe-Trading at the pinned commit in the external archive
  (`../mootrade-reference-archive/Vibe-Trading`); do not install its full
  dependency stack into the MooTrade backend environment.
- Use a separate research virtual environment.
- Keep `ORDER_WRITES_ENABLED=false`. None of the scripts import a broker order
  path, OAuth write scope, `TradingService` or `RiskGate`.
- The 2015-2024 protocol data is development evidence only. The
  `volume-confirmed-relative-strength-v1` hypothesis was rejected by its
  pre-registered rule; do not tune or deploy it.

## Environment

The recorded runs used Python 3.14.5, pandas 3.1.1, numpy 2.5.5 and the
temporary dependency directory `C:\Users\Warren\AppData\Local\Temp\mootrade_vibe_poc`.
That combination ran, but Vibe declares `pandas<3.0.0`, so it is **not** a
supported dependency set. For a supported rerun, use Python 3.11-3.13 and
`requirements.txt` (pandas 2.x). Small floating-point differences are
expected; the protocol conclusions are not sensitive to them.

From the repository root:

```bash
py -3.12 -m venv .venv-vibe-research
.venv-vibe-research/Scripts/python -m pip install -e ".[dev]"
.venv-vibe-research/Scripts/python -m pip install -r evidence/research/vibe-trading-poc-2026-11-18/requirements.txt
```

If dependencies live outside that virtual environment, set
`VIBE_TRADING_DEPS` to their directory; the scripts add it to `sys.path` when
the variable is present.

Verify the pin before running:

```bash
git -C ../mootrade-reference-archive/Vibe-Trading rev-parse HEAD
```

## Phase 2 — engine comparison

Inputs are committed; no Moomoo token or network call is needed.

```bash
.venv-vibe-research/Scripts/python evidence/research/vibe-trading-poc-2026-11-18/run_poc.py
```

Writes `results.json`, `report.md` and `vibe-run/`. Expected result:

- Vibe and MooTrade final value: `$100,089.46`.
- Both total returns: `0.0895%` on `$100,000`.
- Maximum common-session equity difference: below `$1e-10`.
- 349 sessions, 23 round trips, maximum drawdown `-1.2156%`.

`probe_history.py` and `probe_autype.py` regenerate `history-probe.json` and
`autype-probe.json` using read-only Moomoo quote endpoints. They require the
read-only token stored by the backend and refuse a token containing
`trade:write`.

## Phase 3 — frozen protocol evaluation

`protocol-data/daily-bars-2015-2024.json` is committed, so the evaluation is
offline and deterministic:

```bash
.venv-vibe-research/Scripts/python evidence/research/vibe-trading-poc-2026-11-18/run_protocol_eval.py
```

Writes `protocol-results.json`, `protocol-report.md` and `protocol-runs/`.
Expected result (2016-01-04 to 2024-12-31):

| Run | Total return | Sharpe |
|---|---:|---:|
| Strategy | 36.82% | 0.735 |
| SPY at strategy weekly gross | 20.47% | 0.867 |
| SPY constant 30% | 47.89% | 0.846 |
| Equal-weight 20 stocks, 30% gross | 107.48% | 1.367 |
| Cash | 0.00% | n/a |

The pre-registered rejection rule triggers: the strategy beat exposure-matched
SPY but trailed the equal-weight comparator and had a lower Sharpe than all
three equity comparators. Validation checks calendar coverage, OHLC integrity,
chronological order, no bars on or after 2025-01-01, independent reference
selections, target constraints, and truncation/future-perturbation look-ahead
over 235 weeks.

## Re-fetching protocol data

Only needed to reproduce `protocol-data/` from the provider. This is a
read-only fetch of 210 Moomoo `history-kline` requests (20 stocks plus SPY,
2015-2024) and the US trading calendar:

```bash
.venv-vibe-research/Scripts/python evidence/research/vibe-trading-poc-2026-11-18/fetch_protocol_data.py
```

The script loads the repository `.env`, requires the read-only token, refuses
any `trade:write` scope, enforces `ORDER_WRITES_ENABLED=false`, throttles
requests, and never reads a bar on or after 2025-01-01. A Moomoo quote quota
can return `ret_code=-11` after roughly 30 rapid requests; the script pauses
and retries, and per-symbol-year responses are cached.

## Evidence

- `report.md`, `results.json`, `vibe-run/` — Phase 2.
- `protocol-report.md`, `protocol-results.json`, `protocol-runs/` — Phase 3.
- `integration-verdict.md` — Phase 4 recommendation and production boundary.
- `protocol-data/` — provider bars, calendar and request log.
